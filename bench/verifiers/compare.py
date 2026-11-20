"""Check identical cancellation obligations with GPT++, Kani, and CrossHair."""
import argparse
import hashlib
import json
from importlib.metadata import version
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
APP = ROOT / "examples/reservations"
PROPERTIES = ("active_cancel_twice", "repeat_cancel", "unknown_cancel")


def command(args, directory, expected=0):
    run = subprocess.run(args, cwd=directory, text=True, capture_output=True, timeout=180)
    output = run.stdout + run.stderr
    if run.returncode != expected:
        raise RuntimeError(f"{args} exited {run.returncode}\n{output}")
    return output


def require(condition, output):
    if not condition:
        raise ValueError(f"unexpected verifier result\n{output}")


def inject(source, old, new):
    require(source.count(old) == 1, "negative-control edit must match exactly once")
    return source.replace(old, new)


def gpp_study(directory, binary, source):
    path = directory / "booking.gpp"
    path.write_text(source)
    for name in PROPERTIES:
        report = json.loads(command([binary, "prove", path, "--contract", name], directory))
        require(report["contracts"] == [{"name": name, "status": "proved"}], report)
    old = "if booking == Booking::Cancelled { return Change(available, booking, Outcome::Ok); }"
    path.write_text(inject(source, old, old.replace("Change(available,", "Change(available + 1,")))
    report = json.loads(command([binary, "prove", path, "--contract", "repeat_cancel"], directory, 1))
    result, = report["contracts"]
    require(result["name"] == "repeat_cancel" and result["status"] == "refuted", report)
    return {"baseline": "proved", "double_release": result}


def rust_study(directory, binary, source):
    path = directory / "booking.rs"
    path.write_text(source)
    args = [binary, path, "--output-format", "terse"]
    good = command(args, directory)
    harnesses = re.findall(r"Checking harness (\w+)\.\.\.", good)
    require(set(harnesses) == set(PROPERTIES) and "3 successfully verified harnesses, 0 failures" in good, good)
    old = "Booking::Cancelled => (n,"
    path.write_text(inject(source, old, "Booking::Cancelled => (n.checked_add(1).unwrap(),"))
    bad = command([*args, "--harness", "repeat_cancel"], directory, 1)
    require("Verification failed for - repeat_cancel" in bad and "assertion failed: cancel(n, Booking::Cancelled)" in bad, bad)
    return {
        "verifier": next(line for line in good.splitlines() if line.startswith("Kani Rust Verifier ")),
        "backend": next(line for line in good.splitlines() if line.startswith("CBMC ")),
        "baseline": "3 successfully verified harnesses",
        "double_release": "repeat_cancel assertion failed",
    }


def python_study(directory, source):
    # Different module names also prevent timestamp-based .pyc reuse on a fast rerun.
    args = [sys.executable, "-B", "-m", "crosshair", "check", "--analysis_kind=PEP316",
            "--report_all", "--per_condition_timeout=8"]
    good_file = directory / "booking.py"
    bad_file = directory / "faulty.py"
    good_file.write_text(source)
    good = command([*args, good_file], directory)
    expected_lines = {i for i, line in enumerate(source.splitlines(), 1) if "post: __return__" in line}
    verified_lines = {int(i) for i in re.findall(r"booking\.py:(\d+): info: Confirmed over all paths\.", good)}
    require(len(expected_lines) == len(PROPERTIES) and verified_lines == expected_lines, good)
    old = "return n, Booking.CANCELLED, Outcome.OK"
    bad_file.write_text(inject(source, old, "return plus_one(n), Booking.CANCELLED, Outcome.OK"))
    bad = command([*args, bad_file], directory, 1)
    failures = [line.split(": error: ", 1)[1] for line in bad.splitlines() if ": error: " in line and "repeat_cancel(" in line]
    require(len(failures) == 1, bad)
    return {"verifier": version("crosshair-tool"), "baseline": "Confirmed over all paths.",
            "double_release": failures[0]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpp", type=Path, default=ROOT / "target/debug/gpp")
    parser.add_argument("--kani", default="kani")
    parser.add_argument("--output", type=Path, help="also write results as JSON to this file")
    args = parser.parse_args()
    kani = shutil.which(args.kani)
    if not kani:
        parser.error("Kani executable was not found")
    files = [APP / "booking.gpp", APP / "cancellation.proof.gpp.inc", HERE / "booking.rs", HERE / "booking.py"]
    production, obligations, rust, python = [f.read_text() for f in files]
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        result = {
            "properties": list(PROPERTIES),
            "source_sha256": {str(f.relative_to(ROOT)): hashlib.sha256(f.read_bytes()).hexdigest() for f in files},
            "z3": command(["z3", "--version"], directory).strip(),
            "gptpp": gpp_study(directory, args.gpp.resolve(), production + "\n" + obligations),
            "rust": rust_study(directory, Path(kani).resolve(), rust),
            "typed_python": python_study(directory, python),
        }
    report = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(report)
    print(report, end="")


if __name__ == "__main__":
    main()
