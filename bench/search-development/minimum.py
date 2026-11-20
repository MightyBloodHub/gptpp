"""Replay minimum-cost selection on the nine previously published search tasks."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CORPUS = ROOT / "bench/search"
sys.path.insert(0, str(CORPUS))
from corpus import TASKS
from native import Program, run


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpp", type=Path, default=ROOT / "target/debug/gpp")
    parser.add_argument("--write", action="store_true", help="regenerate minimum.json")
    args = parser.parse_args()
    rows = []
    with TemporaryDirectory() as tmp:
        work = Path(tmp)
        binary = work / "gpp"
        shutil.copy2(args.gpp.resolve(), binary)
        binary_hash = digest(binary)
        for task in TASKS:
            adapter = Program(task, "gpp", work / task.name, binary)
            response = run([binary, "complete", adapter.sketch, "--hole", "change",
                            "--search", "minimum", "--limit", "256", "--budget", "10000"])
            if response.returncode not in (0, 1, 3):
                raise RuntimeError(response.stderr or response.stdout)
            report = json.loads(response.stdout)
            score = None
            if response.returncode == 0:
                status, detail = adapter.public(report["selected"], trusted=True)
                if status != "pass":
                    raise ValueError(f"{task.name}: {status}, {detail}")
                score = adapter.hidden()
            row = {"task": task.name, "input_sha256": digest(adapter.sketch),
                   "completion": report, "withheld": score}
            rows.append(row)
            print(task.name, report["status"], report.get("selected", ""),
                  "" if score is None else f"direct errors={score['direct_wrong']}, history errors={score['history_wrong']}")
    data = {"schema": "gpp.development-minimum/1", "gpp_sha256": binary_hash,
            "replay_sha256": digest(Path(__file__)),
            "files_sha256": {p: digest(CORPUS / p) for p in ("corpus.py", "native.py", "engine.py")},
            "rows": rows}
    if args.write:
        (HERE / "minimum.json").write_text(json.dumps(data, indent=2) + "\n")


if __name__ == "__main__":
    main()
