#!/usr/bin/env python3
"""Find a single checked expression edit satisfying every finite source contract."""

import argparse
from contextlib import ExitStack
import itertools
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

from contract_check import verify, witness
import distinguish
import probe
import propose
import repair


# Preserve whitespace and GPT++ line comments around a binary operator.
OPERATOR = re.compile(rb"(?:\s|//[^\r\n]*)*(\|\||&&|==|!=|<=|>=|[+*/%<>-])(?:\s|//[^\r\n]*)*")
SEMANTIC_FAULTS = {"IntegerOverflow", "DivisionByZero", "InvalidBounds"}


def variants(site):
    old = site["text"]
    if "binary_gap" in site:
        data = old.encode()
        start, end = (p - site["start_byte"] for p in site["binary_gap"])
        match = OPERATOR.fullmatch(data[start:end])
        if match:
            operator = match[1].decode()
            for group in repair.OPERATORS:
                if operator in group:
                    for other in group:
                        yield (data[:start + match.start(1)] + other.encode()
                               + data[start + match.end(1):]).decode()
    yield from repair.variants(site)
    locals_ = site["observations"][0]["locals"]
    integers = sorted(name for name, value in locals_.items() if type(value) is int)
    if site["type"] == "I64":
        for flag in sorted(k for k, value in locals_.items() if type(value) is bool):
            yield f"{flag} as I64"
        for left, right in itertools.combinations(integers, 2):
            for function in ("min", "max"):
                yield f"{function}({left}, {right})"


def replacements(site):
    seen = {site["text"].strip()}
    for value in variants(site):
        if value not in seen:
            seen.add(value)
            yield value


def literals(example):
    return [json.dumps(value) for value in example["args"]]


def menu_candidates(args, snapshot, revision):
    menu = distinguish.load_json(args.menu)
    if not isinstance(menu, dict) or menu.get("schema") != "gpp.repair/1":
        raise ValueError("Supply a gpp.repair/1 candidate menu.")
    if menu.get("revision") != revision or menu.get("function") != args.function:
        raise ValueError("Stale revision or different target in candidate menu.")
    if not isinstance(menu.get("candidates"), list):
        raise ValueError("Menu requires an array of candidates.")
    return [row for _, row in distinguish.validated_candidates(args.gpp, snapshot, menu)]


def from_trace(args, snapshot, revision, example):
    trace = json.loads(propose.checked(args.gpp, "trace", snapshot, "--function", args.function,
                                       "--contract", example["contract"], *literals(example)))
    if (trace.get("schema") != "gpp.trace/1" or trace.get("revision") != revision or
            trace.get("entry_kind") != "contract" or trace.get("args") != example["args"] or
            (trace.get("result") is not False and trace.get("fault") not in SEMANTIC_FAULTS)):
        raise ValueError("Contract witness could not be reproduced by the compiler trace.")
    return repair.search_order([trace], [0], replacements)


def search(args, snapshot, work, candidates, report):
    """Replay cached counterexamples cheaply; only the full verifier can accept an edit."""
    witnesses = report["witnesses"]
    witnesses.append(witness(report["baseline"]))
    verified = []
    incomplete = False
    fragment, preview = work / "edit.expr", work / "edit.gpp"
    stop = "menu_complete" if args.menu else "grammar_complete"
    with ExitStack() as session:
        evaluate = None
        for index, candidate in enumerate(candidates, 1):
            if index > args.edits:
                stop, incomplete = "edit_limit", True
                break
            if evaluate is None:
                calls = [(w["contract"], literals(w)) for w in witnesses]
                evaluate = session.enter_context(probe.session(args.gpp, snapshot, args.function,
                                                               report["revision"], work, calls, contracts=True))
            report["tested"] += 1
            reply = evaluate(candidate)
            if reply["status"] == "invalid":
                outcome = {"status": "invalid", "error": reply["error"]}
            else:
                rejection = next((i for i, r in enumerate(reply["outcomes"], 1)
                                  if r.get("result") is False or r.get("fault") in SEMANTIC_FAULTS), None)
                if rejection is not None:
                    outcome = {"status": "rejected", "witness": rejection}
                    report["rejected_by_replay"] += 1
                else:
                    fragment.write_text(candidate["replacement"], encoding="utf-8")
                    command = repair.patch_args(args.gpp, snapshot, args.function, candidate)
                    checked = propose.compiler(*command, fragment, "--expect", report["revision"], "--stdout")
                    if checked.returncode:
                        raise ValueError("Checked probe and editor disagree: " + checked.stderr.decode())
                    preview.write_bytes(checked.stdout)
                    check = verify(args.gpp, preview, args.budget)
                    report["full_checks"] += 1
                    outcome = {"status": check["status"], "checked": check["checked"]}
                    if check["status"] == "passed":
                        report["candidates"].append(candidate)
                        verified.append(check)
                        if not args.menu:
                            stop = "first_verified"
                            break
                    elif check["status"] == "incomplete":
                        incomplete = True
                    else:
                        new = witness(check)
                        if any(w["contract"] == new["contract"] and w["args"] == new["args"] for w in witnesses):
                            raise ValueError("Witness replay and verification disagree.")
                        witnesses.append(new)
                        outcome.update(status="rejected", witness=len(witnesses))
                        session.close()
                        evaluate = None
            if args.menu:
                report["outcomes"].append({"candidate": index, **outcome})

    report["stop_reason"] = stop
    if len(verified) > 1:
        report["status"] = "ambiguous"
    elif verified and (not args.menu or not incomplete):
        report.update(status="verified", selected=report["candidates"][0], verification=verified[0])
    else:
        report["status"] = "incomplete" if incomplete else "no_repair"


def contract_repair(args):
    if args.edits <= 0 or args.budget < 0:
        raise ValueError("--edits must be positive and --budget nonnegative.")
    if args.output and (os.path.lexists(args.output) or not args.output.parent.is_dir()):
        raise ValueError("Supply a new output fragment path in an existing directory.")
    with TemporaryDirectory(prefix="gpp-contract-repair-") as tmp:
        work = Path(tmp)
        snapshot = work / "original.gpp"
        snapshot.write_bytes(args.file.read_bytes())
        baseline = verify(args.gpp, snapshot, args.budget)
        revision = baseline["revision"]
        candidates = None
        if args.menu:
            candidates = menu_candidates(args, snapshot, revision)
        else:
            propose.expression_catalog(args.gpp, snapshot, args.function, revision)
        report = dict(schema="gpp.contract-repair/1", function=args.function, revision=revision,
                      baseline=baseline, status="incomplete", tested=0, full_checks=0, rejected_by_replay=0,
                      witnesses=[], candidates=[], selected=None, verification=None, edit_limit=args.edits)
        if args.menu:
            report["outcomes"] = []
        if baseline["status"] == "counterexample":
            if candidates is None:
                candidates = from_trace(args, snapshot, revision, witness(baseline))
            search(args, snapshot, work, candidates, report)
        else:
            report["stop_reason"] = "baseline_" + baseline["status"]
            if baseline["status"] == "passed":
                report["status"] = "already_passes"
        if propose.checked(args.gpp, "revision", args.file).strip() != revision:
            raise ValueError("Stale revision: source changed during repair.")
        if report["selected"] and args.output:
            candidate = report["selected"]
            report["apply"] = [*repair.patch_args(args.gpp, args.file, args.function, candidate),
                               str(args.output), "--expect", revision, "--verify", "--budget", str(args.budget)]
            propose.publish(args.output, candidate["replacement"] + "\n")
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--function", required=True)
    parser.add_argument("--menu", type=Path, help="classify an existing gpp.repair/1 menu")
    parser.add_argument("--budget", type=int, default=10_000, help="maximum assignments per whole-module verification")
    parser.add_argument("--edits", type=int, default=512, help="maximum candidate edits to check")
    parser.add_argument("--gpp", default=str(propose.ROOT / "target/debug/gpp"))
    parser.add_argument("-o", "--output", type=Path, help="new file for the selected expression")
    try:
        print(json.dumps(contract_repair(parser.parse_args()), ensure_ascii=False))
    except (propose.ProposalError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
