"""Compare full CLI latency while requiring identical repair menus and questions."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import platform
import resource
import statistics
import subprocess
import sys
from tempfile import TemporaryDirectory
import time

import repair_study as study
from bench.policy.upstream import TASKS as TRANSFER

ROOT = study.ROOT
BASELINE_REVISION = "245cb7ea99d834780a9838571d3f6e0af9a467e7"
TASKS = [*study.TASKS, *TRANSFER]


def workloads():
    for task in TASKS:
        yield "repair", task, None
    _, rows = study.read_archive(study.HERE / "results/distinguish.jsonl")
    tasks = {task["id"]: task for task in study.TASKS}
    _, repairs = study.read_archive(study.HERE / "results/repair.jsonl")
    for row in rows:
        task = tasks[row["task"]]
        menu = next(r["product"] for r in repairs if r["task"] == row["task"])
        yield "distinguish", task, (menu, row["pool"])


def execute(root, kind, task, extra):
    with TemporaryDirectory(prefix="gpp-latency-") as temporary:
        work = Path(temporary)
        source = work / "source.gpp"
        source.write_text(study.MODULE + study.source_for(task, "gpp") + study.ENTRY)
        cmd = [sys.executable, "-B", root / "tools" / f"{kind}.py", source,
               "--gpp", root / "target/debug/gpp"]
        if kind == "repair":
            cases = work / "cases.json"
            cases.write_text(json.dumps([dict(function=name, args=args, expected=expected)
                                         for name, args, expected in task["public"]]))
            cmd += ["--function", task["target"], "--cases", cases, "--list"]
        else:
            menu, probes = extra
            menu_file, probe_file = work / "menu.json", work / "probes.json"
            menu_file.write_text(json.dumps(menu))
            probe_file.write_text(json.dumps(probes))
            cmd += ["--menu", menu_file, "--probes", probe_file]
        before = resource.getrusage(resource.RUSAGE_CHILDREN)
        started = time.perf_counter()
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        wall = time.perf_counter() - started
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        if proc.returncode:
            raise ValueError(proc.stderr or proc.stdout)
        value = json.loads(proc.stdout)
        cpu = (after.ru_utime + after.ru_stime) - (before.ru_utime + before.ru_stime)
        return value, dict(wall_seconds=wall, cpu_seconds=cpu)


def manifest(root):
    files = [*sorted((root / "src").glob("*.rs")),
             root / "tools/repair.py", root / "tools/distinguish.py",
             root / "tools/propose.py"]
    helper = root / "tools/probe.py"
    if helper.exists():
        files.append(helper)
    return dict(compiler=sha256((root / "target/debug/gpp").read_bytes()).hexdigest(),
                sources={str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest() for p in files})


def run(args):
    roots = {"previous": args.baseline.resolve(), "current": ROOT}
    meta = dict(study="persistent-probe-latency-v1", baseline_revision=BASELINE_REVISION,
                platform=platform.platform(), python=platform.python_version(),
                versions={k: manifest(v) for k, v in roots.items()}, repetitions=3,
                protocol_sha256=sha256((study.HERE / "probe-protocol.md").read_bytes()).hexdigest(),
                runner_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
    with args.archive.open("x", buffering=1) as stream:
        print(json.dumps(meta), file=stream)
        for kind, task, extra in workloads():
            baseline, observations = None, []
            for repetition in range(3):
                for version in (("previous", "current") if repetition % 2 == 0 else ("current", "previous")):
                    result, timing = execute(roots[version], kind, task, extra)
                    if baseline is None:
                        baseline = result
                    if result != baseline:
                        raise ValueError(f"Behavior changed in {kind}/{task['id']}/{version}")
                    observations.append(dict(version=version, repetition=repetition, **timing))
            row = dict(command=kind, task=task["id"], result=baseline, observations=observations)
            print(json.dumps(row), file=stream)
            print(kind, task["id"], "identical", flush=True)


def report(archive):
    _, rows = study.read_archive(archive)
    print("# Compiler evaluation latency\n")
    print("Three alternating repetitions of each complete public CLI command ran on the same host. "
          "Every parsed result matched exactly across versions and repetitions. The comparison "
          "includes source reads, process startup, candidate checking and execution.\n")
    print("| Command | Task | Previous median s | Current median s | Speedup | Previous CPU s | Current CPU s |")
    print("|---|---|---:|---:|---:|---:|---:|")
    totals = {"previous": 0, "current": 0}
    for row in rows:
        values = {}
        for version in totals:
            group = [v for v in row["observations"] if v["version"] == version]
            values[version] = [statistics.median(v[key] for v in group)
                               for key in ("wall_seconds", "cpu_seconds")]
            totals[version] += values[version][0]
        old, new = values["previous"], values["current"]
        print(f"| {row['command']} | {row['task']} | {old[0]:.3f} | {new[0]:.3f} | "
              f"{old[0]/new[0]:.2f}× | {old[1]:.3f} | {new[1]:.3f} |")
    print(f"\nThe sum of workload medians fell from {totals['previous']:.3f} to "
          f"{totals['current']:.3f} seconds ({totals['previous']/totals['current']:.2f}× faster). "
          "Menus and questions matched, so acceptance and model usage are unchanged by this optimization. "
          "Both versions used debug compiler builds. Timings depend on the host and workload.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--baseline", type=Path, default=ROOT / "target/probe-baseline")
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()
    if args.report:
        report(args.archive)
    else:
        run(args)
