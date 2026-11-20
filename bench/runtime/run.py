"""Compare correct scalar programs through equivalent checksum loops."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import platform
import re
import statistics
import subprocess
import sys
from tempfile import TemporaryDirectory
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bench/expression"))
import repair_study as study

ITERATIONS = 2_000_000
CALLS = {
    "redis_lru_timestamp": ("access_stamp", ["i % 16777216", "i % 10001", "1000"]),
    "fastled_fixed_scale": ("scale_channel", ["i % 256", "(i / 256) % 256", "i % 2 == 0"]),
    "go_footer_year_end": ("period_end", ["1600 + i % 801", "(i * 17) % 31536000"]),
}


def source(task, language):
    name, args = CALLS[task["id"]]
    call = f"{name}({', '.join(args)})"
    code = study.source_for(task, language, "reference")
    if language == "python":
        call = call.replace(" / ", " // ")
        return code + (
            f"\ndef main() -> int:\n    total = 0\n    i = 0\n    while i < {ITERATIONS}:\n"
            f"        total += {call}\n        i += 1\n    return total\nprint(main())\n"
        )
    body = f"var total = 0; var i = 0; while i < {ITERATIONS} {{ total += {call}; i += 1; }}"
    if language == "gpp":
        return study.MODULE + code + f"\npub fn main() -> I64 !{{}} {{ {body} return total; }}\n"
    return code + "\nfn main() { " + body.replace("var ", "let mut ").replace("= 0;", "= 0_i64;") + ' println!("{}", total); }\n'


def run(archive):
    records = []
    with TemporaryDirectory(prefix="gpp-runtime-") as directory:
        work = Path(directory)
        evaluator = study.base.prior.Tools(ROOT, ROOT / "target/debug/gpp")
        for task in study.TASKS:
            for language in ("gpp", "rust", "python"):
                status, detail = study.evaluate(evaluator, language, study.source_for(task, language, "reference"),
                                                [*task["public"], *task["heldout"]])
                if status != "pass":
                    raise ValueError(f"Reference {task['id']}/{language}: {detail}")
        for task in study.TASKS:
            commands, files, builds = {}, {}, {}
            for language, suffix in (("gpp", "gpp"), ("rust", "rs"), ("python", "py")):
                file = work / f"{task['id']}.{suffix}"
                file.write_text(source(task, language))
                files[language] = file
                binary = work / (task["id"] + "-" + language)
                if language == "gpp":
                    build = [ROOT / "target/debug/gpp", "build", "-O2", file, "-o", binary]
                elif language == "rust":
                    build = ["rustc", "--edition=2024", "-C", "opt-level=2", "-C", "overflow-checks=yes",
                             file, "-o", binary]
                else:
                    build = [sys.executable, "-m", "py_compile", file]
                began = time.perf_counter()
                subprocess.run(build, check=True, capture_output=True, text=True, timeout=120)
                builds[language] = time.perf_counter() - began
                commands[language] = [sys.executable, "-B", file] if language == "python" else [binary]
            checksum = None
            samples = {lang: [] for lang in commands}
            for repetition in range(3):
                order = ("gpp", "rust", "python") if repetition % 2 == 0 else ("python", "rust", "gpp")
                for language in order:
                    began = time.perf_counter()
                    proc = subprocess.run(["/usr/bin/time", "-l", *commands[language]],
                                          capture_output=True, text=True, timeout=120)
                    elapsed = time.perf_counter() - began
                    if proc.returncode:
                        raise ValueError(proc.stderr)
                    result = int(proc.stdout.strip())
                    if checksum is None:
                        checksum = result
                    if result != checksum:
                        raise ValueError("Language results differ.")
                    peak = re.search(r"(\d+)\s+maximum resident set size", proc.stderr)
                    if peak is None:
                        raise ValueError("Peak memory missing.")
                    samples[language].append(dict(wall_seconds=elapsed, peak_rss_bytes=int(peak[1])))
            records.append(dict(task=task["id"], iterations=ITERATIONS, checksum=checksum,
                                build_seconds=builds, samples=samples,
                                sources={lang: file.read_text() for lang, file in files.items()}))
    meta = dict(study="scalar-runtime-v1", platform=platform.platform(), python=sys.version,
                rustc=subprocess.check_output(["rustc", "--version"], text=True).strip(),
                gpp_sha256=sha256((ROOT / "target/debug/gpp").read_bytes()).hexdigest(),
                runner_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                protocol_sha256=sha256(Path(__file__).with_name("README.md").read_bytes()).hexdigest())
    with archive.open("x") as stream:
        for record in [meta, *records]:
            print(json.dumps(record), file=stream)


def report(archive):
    _, rows = study.read_archive(archive)
    print("# Scalar program runtime and memory\n")
    print("Each correct reference runs two million calls in a checksum loop. Every implementation passed "
          "the original public and withheld cases, and all checksum results agree. Runtime is the "
          "median of three process executions including startup. Peak resident memory is measured by "
          "macOS time -l. Native builds use optimization level 2 and checked signed arithmetic.\n")
    print("| Task | Language | Build/check s | Runtime median s | Peak RSS median MiB |")
    print("|---|---|---:|---:|---:|")
    for row in rows:
        for language in ("gpp", "rust", "python"):
            samples = row["samples"][language]
            wall = statistics.median(r["wall_seconds"] for r in samples)
            rss = statistics.median(r["peak_rss_bytes"] for r in samples) / 1048576
            print(f"| {row['task']} | {language} | {row['build_seconds'][language]:.3f} | {wall:.4f} | {rss:.2f} |")
    print("\nThe single build measurement is descriptive. Python's entry is bytecode compilation. "
          "GPT++ and Rust produce native executables. The loops cover these declared scalar inputs, "
          "and compiler optimization can simplify them. Tiny native execution times are sensitive to "
          "process startup and host scheduling. General application performance remains unmeasured.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()
    if args.report:
        report(args.archive)
    else:
        run(args.archive)
