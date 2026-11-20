"""Validate the frozen piecewise search on the two corpora available to its authors."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BLOCKS = {"original-nine": "bench/search", "external-twelve": "bench/search-followup"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("block", choices=BLOCKS)
    parser.add_argument("--gpp", type=Path, default=ROOT / "target/release/gpp")
    parser.add_argument("--write", action="store_true", help="replace this block's capture")
    options = parser.parse_args()
    corpus_dir = ROOT / BLOCKS[options.block]
    adapters_dir = ROOT / "bench/search"
    sys.path[:0] = [str(corpus_dir), str(adapters_dir)]
    from corpus import TASKS
    from native import Program, run

    rows = []
    with TemporaryDirectory() as tmp:
        work = Path(tmp)
        binary = work / "gpp"
        shutil.copy2(options.gpp.resolve(), binary)
        binary_hash = digest(binary)
        for task in TASKS:
            program = Program(task, "gpp", work / task.name, binary)
            response = run([binary, "complete", program.sketch, "--hole", "change",
                            "--search", "piecewise", "--limit", "256", "--budget", "10000"])
            if response.returncode not in (0, 1, 3):
                raise RuntimeError(response.stderr or response.stdout)
            report = json.loads(response.stdout)
            score = None
            if response.returncode == 0:
                status, detail = program.public(report["selected"], trusted=True)
                if status != "pass":
                    raise ValueError((task.name, status, detail))
                score = program.hidden()
            rows.append({"task": task.name, "input_sha256": digest(program.sketch),
                         "completion": report, "withheld": score})
            print(task.name, report["status"], "" if score is None else
                  f"direct errors={score['direct_wrong']}, history errors={score['history_wrong']}")
    sources = [corpus_dir / "corpus.py", adapters_dir / "native.py", adapters_dir / "engine.py"]
    record = {"schema": "gpp.development-piecewise/1", "block": options.block,
              "gpp_sha256": binary_hash, "replay_sha256": digest(Path(__file__)),
              "files_sha256": {str(p.relative_to(ROOT)): digest(p) for p in sources},
              "rows": rows}
    archive = HERE / f"piecewise-{options.block}.json"
    if options.write:
        archive.write_text(json.dumps(record, indent=2) + "\n")
    else:
        saved = json.loads(archive.read_text())
        for field in ("rows", "files_sha256", "replay_sha256"):
            if saved[field] != record[field]:
                raise ValueError(f"{archive.name} differs in {field}")
        print("Matched the archived compiler reports and independent scores.")


if __name__ == "__main__":
    main()
