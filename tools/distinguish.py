#!/usr/bin/env python3
"""Find the supplied call that distinguishes the most pairs of checked repair candidates."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory

import propose
from repair import patch_args


def load_json(path):
    def unique(pairs):
        result = dict(pairs)
        if len(result) != len(pairs):
            raise ValueError(f"{path}: duplicate JSON field")
        return result

    return json.loads(path.read_bytes(), object_pairs_hook=unique)


def selected_ids(raw, size):
    if raw is None:
        return set(range(1, size + 1))
    if not re.fullmatch(r"[1-9][0-9]*(?:,[1-9][0-9]*)*", raw):
        raise ValueError("--candidates expects comma-separated positive menu IDs")
    ids = [int(i) for i in raw.split(",")]
    if len(set(ids)) != len(ids) or max(ids) > size:
        raise ValueError("--candidates needs distinct IDs present in the original menu")
    return set(ids)


def read_probes(path, target, declarations):
    rows = load_json(path)
    if not isinstance(rows, list) or not rows:
        raise ValueError("Supply a nonempty JSON list of unlabeled probe calls.")
    probes = []
    for i, row in enumerate(rows, 1):
        if not isinstance(row, dict) or set(row) not in ({"args"}, {"function", "args"}):
            raise ValueError(f"Probe {i} requires args and accepts an optional function name.")
        name, args = row.get("function", target), row["args"]
        if not isinstance(name, str) or name not in declarations:
            raise ValueError(f"Probe {i} has an unknown function: {name!r}")
        params = propose.parameters(declarations[name])
        if not isinstance(args, list) or len(args) != len(params):
            raise ValueError(f"Probe {i} needs {len(params)} positional arguments for {name}.")
        literals = [propose.case_literal(v, ty, f"Probe {i}, {param}") for v, (param, ty) in zip(args, params)]
        probes.append((name, args, literals))
    return probes


def previews(binary, work, snapshot, menu, subset):
    target, revision, candidates = menu["function"], menu["revision"], menu["candidates"]
    catalog = propose.expression_catalog(binary, snapshot, target, revision)
    spans = {(row["start_byte"], row["end_byte"]): row["text"] for row in catalog["expressions"]}
    paths = {}
    fragment = work / "candidate.expr"
    for i, row in enumerate(candidates, 1):
        if not isinstance(row, dict) or set(row) != {"start_byte", "end_byte", "old", "replacement"}:
            raise ValueError(f"Candidate {i} needs its byte range, original text and replacement.")
        start, end = row["start_byte"], row["end_byte"]
        if (type(start) is not int or type(end) is not int or not isinstance(row["old"], str)
                or spans.get((start, end)) != row["old"]):
            raise ValueError(f"Candidate {i} disagrees with the checked expression catalog.")
        if not isinstance(row["replacement"], str) or not row["replacement"].strip():
            raise ValueError(f"Candidate {i} requires a nonempty replacement expression.")
        fragment.write_text(row["replacement"], encoding="utf-8")
        source = propose.checked(*patch_args(binary, snapshot, target, row), fragment, "--expect", revision, "--stdout")
        if i in subset:
            file = work / f"candidate-{i}.gpp"
            file.write_bytes(source.encode())
            paths[i] = file
    return paths


def outcome(binary, file, target, call, literals, result_type):
    data = json.loads(propose.checked(binary, "trace", file, "--function", target, "--call", call, *literals))
    if data.get("schema") != "gpp.trace/1" or ("result" in data) == ("fault" in data):
        raise ValueError("Expected a compiler trace with exactly one result or fault.")
    if "fault" in data:
        return "fault", data["fault"]
    propose.case_literal(data["result"], result_type, "trace result")
    return "result", data["result"]


def distinguish(args):
    menu = load_json(args.menu)
    if (not isinstance(menu, dict) or menu.get("schema") != "gpp.repair/1"
            or not isinstance(menu.get("function"), str) or not isinstance(menu.get("candidates"), list)):
        raise ValueError("Supply a gpp.repair/1 menu with a target function and candidates.")
    target = menu["function"]
    subset = selected_ids(args.candidates, len(menu["candidates"]))
    with TemporaryDirectory(prefix="gpp-distinguish-") as directory:
        work = Path(directory)
        snapshot = work / "base.gpp"
        snapshot.write_bytes(args.file.read_bytes())
        base = propose.checked(args.gpp, "revision", snapshot).strip()
        if menu.get("revision") != base:
            raise ValueError("Stale revision: menu and source differ.")
        dump = propose.checked(args.gpp, "ast", snapshot)
        declarations = {fn["name"]: fn for fn in propose.FUNCTION.finditer(dump)}
        probes = read_probes(args.probes, target, declarations)
        paths = previews(args.gpp, work, snapshot, menu, subset)
        best, best_score, tested = None, 0, 0
        if len(paths) >= 2:
            for call, values, literals in probes:
                groups = {}
                pairs = 0
                for seen, (i, file) in enumerate(paths.items()):
                    key = outcome(args.gpp, file, target, call, literals, declarations[call]["result"])
                    group = groups.setdefault(key, [])
                    # All earlier candidates outside this outcome group disagree.
                    pairs += seen - len(group)
                    group.append(i)
                tested += 1
                if pairs > best_score:
                    best_score = pairs
                    best = dict(function=call, args=values, separated_pairs=pairs,
                                outcomes=[{kind: value, "candidates": ids}
                                          for (kind, value), ids in groups.items()])
        if propose.checked(args.gpp, "revision", args.file).strip() != base:
            raise ValueError("Stale revision: source changed during the comparison.")
    return dict(schema="gpp.distinguish/1", revision=base, function=target,
                status="question" if best else "indistinguishable",
                candidate_count=len(subset), probes_tested=tested, question=best)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--menu", required=True, type=Path)
    parser.add_argument("--probes", required=True, type=Path)
    parser.add_argument("--candidates", help="comma-separated 1-based IDs from the original menu")
    parser.add_argument("--gpp", default=str(propose.ROOT / "target/debug/gpp"))
    try:
        print(json.dumps(distinguish(parser.parse_args()), ensure_ascii=False))
    except (OSError, ValueError, subprocess.TimeoutExpired, propose.ProposalError) as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
