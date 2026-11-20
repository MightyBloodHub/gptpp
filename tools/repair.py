#!/usr/bin/env python3
"""Search one GPT++ expression edit against public examples, then optionally ask a model to choose."""

import argparse
from collections import deque
import itertools
import json
import os
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory

import propose


DEFAULT_BUDGET = 512
MENU_LIMIT = 12
ATOM = r"(?:[A-Za-z_][A-Za-z_0-9]*|[0-9]+)"
OPERATORS = (("+", "-", "*", "/", "%"), ("==", "!=", "<", "<=", ">", ">="), ("&&", "||"))


def variants(site):
    old = site["text"]
    locals_ = site["observations"][0]["locals"]
    ints = sorted(k for k, v in locals_.items() if type(v) is int)
    bools = sorted(k for k, v in locals_.items() if type(v) is bool)
    # An atom can be placed directly in an infix expression. Group compound source.
    term = old if re.fullmatch(ATOM, old) else f"({old})"
    kind = site["type"]

    # Try neighboring operators before constructing a new expression from scope.
    match = re.fullmatch(rf"({ATOM})\s*(\|\||&&|==|!=|<=|>=|[+*/%<>-])\s*({ATOM})", old)
    if match:
        lhs, op, rhs = match.groups()
        for group in OPERATORS:
            if op in group:
                for other in group:
                    if other != op:
                        yield f"{lhs} {other} {rhs}"

    if kind == "I64":
        for op in ("+", "-"):
            yield f"{term} {op} 1"
        for flag in bools:
            for op in ("+", "-"):
                yield f"{term} {op} (if {flag} {{ 1 }} else {{ 0 }})"
        yield from ints
        yield from ("0", "1")
        for op in OPERATORS[0]:
            pairs = (itertools.combinations_with_replacement(ints, 2)
                     if op in ("+", "*") else itertools.product(ints, repeat=2))
            for a, b in pairs:
                yield f"{a} {op} {b}"
    elif kind == "Bool":
        yield f"!({old})"
        yield from bools
        yield from ("true", "false")
        for b in bools:
            yield f"!{b}"
        for op in OPERATORS[1]:
            for a, b in itertools.product(ints, [*ints, "0", "1"]):
                yield f"{a} {op} {b}"
        for a, b in itertools.combinations(bools, 2):
            yield f"{a} && {b}"
            yield f"{a} || {b}"


def distinct_variants(site):
    seen = {site["text"].strip()}
    for replacement in variants(site):
        if replacement not in seen:
            seen.add(replacement)
            yield replacement


def search_order(traces, failures):
    # Changing an unvisited site cannot affect that failing deterministic execution.
    # Prefer sites that ran on fewer already-correct examples. Give each eligible
    # site one turn per round so a large scope cannot monopolize the edit budget.
    failing = [traces[i]["expressions"] for i in failures]
    passing = [trace["expressions"] for i, trace in enumerate(traces) if i not in failures]
    ranked = []
    for index, site in enumerate(failing[0]):
        if site["type"] != "Unit" and all(sites[index]["observations"] for sites in failing):
            ranked.append((sum(sites[index]["hits"] > 0 for sites in passing), index, site))
    pending = deque((site, distinct_variants(site)) for _, _, site in sorted(ranked))
    while pending:
        site, fragments = pending.popleft()
        fragment = next(fragments, None)
        if fragment is not None:
            yield dict(start_byte=site["start_byte"], end_byte=site["end_byte"],
                       old=site["text"], replacement=fragment)
            pending.append((site, fragments))


def patch_args(binary, path, function, candidate):
    span = f"{candidate['start_byte']}:{candidate['end_byte']}"
    return [str(binary), "edit", str(path), "--function", function, "--at", span, "--expr"]


def search(args, snapshot, work, cases, base):
    traces, failures, observations = [], [], []
    for i, case in enumerate(cases):
        trace = json.loads(propose.checked(args.gpp, "trace", snapshot, "--function", args.function,
                                           "--call", case.function, *case.args))
        if trace["schema"] != "gpp.trace/1" or trace["revision"] != base:
            raise ValueError("Compiler trace belongs to a different schema or source revision.")
        actual = (f"fault: {trace['fault']}" if "fault" in trace else
                  propose.case_literal(trace["result"], case.result_type, "trace result"))
        observations.append(dict(call=case.call(), actual=actual, expected=case.expected))
        if actual != case.expected:
            failures.append(i)
        traces.append(trace)

    result = dict(schema="gpp.repair/1", revision=base, function=args.function,
                  status="already_passes" if not failures else "no_candidates", observations=observations,
                  tested=0, budget=args.budget, exhausted=False, stop_reason="already_passes",
                  candidates=[], selected=None)
    if not failures:
        return result

    result["stop_reason"] = "grammar_complete"
    fragment = work / "probe.expr"
    # Check the original failures first. Every survivor still has to pass every case.
    prioritized = [cases[i] for i in failures] + [c for i, c in enumerate(cases) if i not in failures]
    for candidate in search_order(traces, failures):
        if result["tested"] >= args.budget:
            result.update(exhausted=True, stop_reason="budget")
            break
        fragment.write_text(candidate["replacement"], encoding="utf-8")
        # The snapshot is private and immutable. The final application targets the user's
        # original revision. The compiler supplies exactly the same grouping in both edits.
        patch = patch_args(args.gpp, snapshot, args.function, candidate)
        preview = propose.compiler(*patch, fragment, "--stdout")
        result["tested"] += 1
        if preview.returncode:
            if b"error[GPP-" in preview.stderr:
                continue
            raise propose.ProposalError(preview.stderr.decode(errors="replace").strip())
        try:
            propose.check_cases(args.gpp, preview.stdout, work, prioritized)
        except propose.CaseFailure:
            continue
        result["candidates"].append(candidate)
        if len(result["candidates"]) == MENU_LIMIT:
            result["stop_reason"] = "menu_full"
            break
    if result["candidates"]:
        result["status"] = "listed"
    return result


def select(args, result, target):
    model, *_ = propose.local_model(args.model, args.port)
    entries = []
    for i, candidate in enumerate(result["candidates"], 1):
        entries.append(f"{i}. bytes {candidate['start_byte']}..{candidate['end_byte']}: "
                       f"{candidate['old']}  =>  {candidate['replacement']}")
    observations = [f"{o['call']} returned {o['actual']}, expected {o['expected']}"
                    for o in result["observations"]]
    prompt = "\n".join([
        "Choose a single GPT++ edit that implements the specification for all valid inputs.",
        args.task, "Original target:", target, "Supplied examples before repair:", *observations,
        "Each edit below independently passes every supplied example:", *entries,
        "Choose the edit that generalizes. Choose 0 if none satisfies the specification.",
    ])
    ids = list(range(len(entries) + 1))
    schema = {"type": "object", "properties": {"choice": {"type": "integer", "enum": ids}},
              "required": ["choice"], "additionalProperties": False}
    request = dict(model=model, prompt=prompt, format=schema, stream=False, keep_alive="3m",
                   options=dict(seed=42, temperature=0, num_ctx=2048, num_predict=48))
    reply = propose.ollama(args.port, "generate", request)
    if reply.get("done") is not True or not isinstance(reply.get("response"), str):
        raise ValueError("Ollama returned an incomplete generation.")
    fields = json.loads(reply["response"], object_pairs_hook=list)
    if not (isinstance(fields, list) and len(fields) == 1 and isinstance(fields[0], tuple)
            and fields[0][0] == "choice" and type(fields[0][1]) is int and fields[0][1] in ids):
        raise ValueError("Expected one integer choice from the checked menu.")
    return fields[0][1]


def repair(args):
    if not args.list and (not args.task or not args.task.strip() or args.output is None):
        raise ValueError("Model selection requires --task and -o.")
    if args.list and args.output is not None:
        raise ValueError("--list prints the candidate menu. Omit -o.")
    if args.output is not None and (os.path.lexists(args.output) or not args.output.parent.is_dir()):
        raise ValueError("Supply a new fragment path in an existing directory.")
    if args.budget < 1:
        raise ValueError("--budget must be positive.")
    source = args.file.read_bytes()
    with TemporaryDirectory(prefix="gpp-repair-") as scratch:
        work = Path(scratch)
        snapshot = work / "base.gpp"
        snapshot.write_bytes(source)
        base = propose.checked(args.gpp, "revision", snapshot).strip()
        dump = propose.checked(args.gpp, "ast", snapshot)
        fn, _ = propose.target_context(dump, args.function)
        declarations = {f["name"]: f for f in propose.FUNCTION.finditer(dump)}
        cases = propose.load_cases(args.cases, args.function, declarations)
        result = search(args, snapshot, work, cases, base)
        choice = None
        if result["candidates"] and not args.list:
            choice = select(args, result, fn[0])
            result.update(status="selected" if choice else "abstained", selected=choice or None)
        if propose.checked(args.gpp, "revision", args.file).strip() != base:
            raise ValueError("Source changed during repair (stale revision).")
        if choice:
            candidate = result["candidates"][choice - 1]
            result["apply"] = [*patch_args(args.gpp, args.file, args.function, candidate),
                               str(args.output), "--expect", base]
            propose.publish(args.output, candidate["replacement"] + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--function", required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET, help="maximum edits to check")
    parser.add_argument("--list", action="store_true", help="emit public-passing candidates offline")
    parser.add_argument("--task")
    parser.add_argument("--model", default=propose.MAINTENANCE_MODEL)
    parser.add_argument("--port", type=int, default=11434)
    parser.add_argument("--gpp", default=str(propose.ROOT / "target/debug/gpp"))
    parser.add_argument("-o", "--output", type=Path)
    try:
        print(json.dumps(repair(parser.parse_args()), ensure_ascii=False))
    except (propose.ProposalError, ValueError, OSError) as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
