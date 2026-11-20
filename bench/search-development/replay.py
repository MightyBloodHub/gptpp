"""Replay the published stateful tasks before and after the synthesis change."""
import argparse
from collections import Counter
from hashlib import sha256
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
HISTORY = ROOT / "bench/stateful"
BASE = "8359fc699e2d528ac01f82f802b236f18a063227"
sys.path.insert(0, str(HISTORY))
from adapters import Adapter, HOLE
from compare import hidden
from tasks import TASKS, oracle


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def old_build(work):
    dest = work / "baseline-source"
    dest.mkdir()
    archive = subprocess.check_output(
        ["git", "archive", BASE, "Cargo.toml", "Cargo.lock", "rust-toolchain.toml", "src"],
        cwd=ROOT,
    )
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        for entry in tar:
            rel = Path(entry.name)
            if entry.isfile() and not rel.is_absolute() and ".." not in rel.parts:
                path = dest / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(tar.extractfile(entry).read())
    subprocess.run(["cargo", "build", "--offline", "--locked"], check=True, cwd=dest)
    return dest / "target/debug/gpp"


def score(adapter, mode, limit):
    args = [adapter.binary, "complete", adapter.file, "--hole", HOLE,
            "--limit", str(limit), "--budget", "10000"]
    if mode != "baseline":
        args.extend(["--search", mode])
    p = subprocess.run(args, capture_output=True, text=True, timeout=60)
    if p.returncode not in (0, 1, 3):
        raise RuntimeError(p.stderr or p.stdout)
    report = json.loads(p.stdout)
    if ((p.returncode == 0) != (report["status"] == "verified")
            or report["tested"] > limit
            or report["revision"] != "sha256:" + digest(adapter.file)):
        raise ValueError(report)
    row = {"task": adapter.task.name, "source_sha256": digest(adapter.file),
           "mode": mode, "limit": limit, "report": report, "hidden": None}
    if p.returncode == 0:
        expr = report["selected"]
        validation = adapter.fill(expr)
        if validation[0] != "pass":
            raise ValueError(f"Selected expression failed replay: {validation}")
        row["hidden"], _ = hidden(adapter)
    return row


def collect(args, tmp):
    baseline = args.baseline_gpp.resolve() if args.baseline_gpp else old_build(tmp)
    before, after = tmp / "before", tmp / "after"
    shutil.copy2(baseline, before)
    shutil.copy2(args.gpp.resolve(), after)
    rows = []
    for task in TASKS:
        for mode in ["baseline", "grammar", "hybrid"]:
            adapter = Adapter("gpp", task, tmp / task.name / mode,
                              before if mode == "baseline" else after, Path(sys.executable), oracle)
            for limit in [64, 256]:
                rows.append(score(adapter, mode, limit))
    return {"schema": "gpp.historical-search/1", "baseline_commit": BASE,
            "binaries_sha256": {"baseline": digest(before), "current": digest(after)},
            "task_sources_sha256": {name: digest(HISTORY / name)
                                    for name in ["tasks.py", "adapters.py", "compare.py"]},
            "replay_sha256": digest(Path(__file__)), "rows": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpp", type=Path, default=ROOT / "target/debug/gpp")
    parser.add_argument("--baseline-gpp", type=Path, help="use an already built baseline executable")
    parser.add_argument("--write", action="store_true", help="write the evidence JSON after all trials")
    args = parser.parse_args()
    with TemporaryDirectory() as tmp:
        data = collect(args, Path(tmp))
    if args.write:
        (HERE / "results.json").write_text(json.dumps(data, indent=2) + "\n")
    for mode in ["baseline", "grammar", "hybrid"]:
        for limit in [64, 256]:
            counts = Counter()
            for r in data["rows"]:
                if r["mode"] == mode and r["limit"] == limit:
                    outcome = ("hidden pass" if r["hidden"]["wrong"] == 0 else "hidden fail"
                               ) if r["hidden"] else r["report"]["status"]
                    counts[outcome] += 1
            print(mode, limit, dict(counts))


if __name__ == "__main__":
    main()
