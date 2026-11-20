#!/usr/bin/env python3
"""Recover the recorded expression, fill the original hole and test the native library from Python."""

import argparse
import ctypes
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BENCH = ROOT / "bench/stateful"
sys.path.insert(0, str(BENCH))
from adapters import Adapter, checked, gpp_program, same  # noqa: E402
from tasks import TASKS, oracle, withheld  # noqa: E402


def replay(binary, archive, work):
    task = next(t for t in TASKS if t.name == "run_record")
    rows = [json.loads(line) for line in archive.read_text().splitlines()]
    label = ("qwen2.5-coder:7b", task.name, "gpp")
    (trial,) = [
        r for r in rows if r.get("kind") == "trial" and (r["model"], r["task"], r["language"]) == label
    ]
    (call,) = [r for r in rows if r.get("kind") == "call" and (r["model"], r["task"], r["language"]) == label]
    code = json.loads(call["reply"]["response"])["expression"]
    if not trial["first_accepted"] or code != trial["attempts"][0]["expression"]:
        raise ValueError("Saved expression and trial decision differ.")
    work.mkdir(parents=True, exist_ok=True)
    original, fragment, output = work / "original.gpp", work / "model.expr", work / "checked.gpp"
    original.write_text(gpp_program(task, None, oracle))
    fragment.write_text(code + "\n")
    compiled = checked([binary, "complete", original, "--hole", "change", "--fill", fragment, "--stdout"])
    output.write_text(compiled)
    standalone = HERE / "streak_counter.gpp"
    full = standalone.read_text()
    marker = "// Scalar ABI added after scoring."
    if full[: full.index(marker)].rstrip() != compiled.rstrip():
        raise ValueError("The standalone program differs from the checked model completion.")
    # Use the benchmark's real native fill/run adapter for independent interpreter scoring.
    ad = Adapter("gpp", task, work / "interpreter", binary, Path(sys.executable), oracle)
    if ad.fill(code)[0] != "pass":
        raise ValueError("The recovered expression failed the public checks.")
    traces = withheld(task)
    observed = ad.observe(traces)
    expected = [oracle(task, trace) for trace in traces]
    if not same(observed, expected):
        raise ValueError("A withheld interpreter trace failed.")
    shared = work / ("streak.dylib" if sys.platform == "darwin" else "streak.so")
    checked([binary, "library", standalone, "-O2", "-o", shared])
    library = ctypes.CDLL(str(shared.resolve()))
    field = library.gpp_v1_next_field
    integer = ctypes.c_int64
    field.argtypes = [integer, integer, integer, integer, ctypes.POINTER(integer)]
    field.restype = ctypes.c_int32
    for trace, truth in zip(traces, expected, strict=True):
        state = (0, 0)
        for event in trace:
            pair = []
            for which in (0, 1):
                value = integer()
                status = field(*state, "ABC".index(event), which, ctypes.byref(value))
                if status:
                    raise ValueError(f"Native ABI fault {status} after {trace}.")
                pair.append(value.value)
            state = tuple(pair)
        if state != truth:
            raise ValueError(f"Native end state {state} differs from {truth} on {trace}.")
    print(f"Recovered original Qwen expression: {code}")
    print(
        f"Passed {len(task.public)} public contracts and all {len(traces)} withheld end states in both the GPT++ interpreter and the native library loaded by Python."
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--gpp", type=Path, default=ROOT / "target/debug/gpp")
    cli.add_argument("--archive", type=Path, default=BENCH / "results.jsonl")
    cli.add_argument(
        "--output-dir",
        type=Path,
        help="keep original source, captured fragment, completed source and library",
    )
    args = cli.parse_args()
    if args.output_dir:
        if args.output_dir.exists() and (not args.output_dir.is_dir() or any(args.output_dir.iterdir())):
            cli.error("--output-dir must be a new or empty directory")
        replay(args.gpp.resolve(), args.archive, args.output_dir)
    else:
        with TemporaryDirectory(prefix="gpp-streak-replay-") as tmp:
            replay(args.gpp.resolve(), args.archive, Path(tmp))
