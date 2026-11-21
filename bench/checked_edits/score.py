"""Independently score closed decisions; no model interface or calls to the repair policy."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import monotonic

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import probe
from public import TASKS, literal, sketch
from sealed import scalar_cases, histories
import native_controls as native


def gpp_observe(task, expr, inputs, work):
    work.mkdir(parents=True, exist_ok=True)
    binary = ROOT / "target/release/gpp"
    src, frag = work / "score.gpp", work / "slot.expr"
    # Use the checked slot again before sending the closed program to probe.
    src.write_text(sketch(task).split("contract sample_0")[0] + "contract ready() { true }\n")
    frag.write_text(expr)
    rev = "sha256:" + sha256(src.read_bytes()).hexdigest()
    result = subprocess.run([binary, "complete", src, "--hole", "change", "--fill", frag,
                             "--expect", rev, "--stdout"], timeout=30, capture_output=True, check=True)
    marker = b"fn marker() -> I64 !{} { return 0; }\n"
    data = result.stdout + marker
    src.write_bytes(data)
    site = len(data) - len(marker) + marker.index(b"0;")
    calls = [("update", list(map(literal, x))) for x in inputs]
    with probe.session(binary, src, "marker", "sha256:" + sha256(data).hexdigest(), work, calls) as evaluate:
        row = evaluate(dict(start_byte=site, end_byte=site + 1, replacement="0"))
    return [r.get("result") for r in row["outcomes"]]


def score(task, lang, expression, work):
    if task.stateful:
        tests = list(histories(task))
    else:
        tests = [(x, [(x, y)]) for x, y in scalar_cases(task.name)]
    inputs = list(dict.fromkeys(x for _, steps in tests for x, _ in steps))
    values = (gpp_observe(task, expression, inputs, work) if lang == "gpp"
              else native.observe(lang, task, expression, inputs, work))
    observed = dict(zip(inputs, values, strict=True))
    first, wrong = None, 0
    for case, steps in tests:
        for i, (x, y) in enumerate(steps, 1):
            actual = observed[x]
            if type(y) is not type(actual) or y != actual:
                first = first or dict(case=case, first_divergent_step=i, inputs=x, expected=y, actual=actual)
                wrong += 1
                break
    return dict(total=len(tests), wrong=wrong, first_error=first,
                outcomes_sha256=sha256(json.dumps(values).encode()).hexdigest())


def main(output):
    log = output / "decisions.jsonl"
    rows = [json.loads(line) for line in log.read_text().splitlines()]
    trials = [r for r in rows if r["kind"] == "trial"]
    names = {r["trial"] for r in trials}
    expected = {f"{t.name}/{lang}/{arm}" for t in TASKS for lang in ("gpp", "python", "rust")
                for arm in ("direct", "direct_retry", "direct_witness", "search", "workflow")}
    if names != expected or len(trials) != len(expected) or rows[-1] != dict(
            kind="closed", ended_utc=rows[-1].get("ended_utc"), count=len(expected)):
        raise ValueError("Scoring requires the complete closed roster")
    receipt = dict(decisions_sha256=sha256(log.read_bytes()).hexdigest(), trials={}, calibration={})
    by_name = {t.name: t for t in TASKS}
    with TemporaryDirectory(prefix="closed-scorer-") as tmp:
        work = Path(tmp)
        # Scoring includes its own native positive and negative controls, only after decisions close.
        start = monotonic()
        for task in TASKS:
            for lang in ("gpp", "python", "rust"):
                key = task.name + "/" + lang
                cases = {}
                for kind, expr in [("reference", task.reference), ("mutant", task.previous)]:
                    cases[kind] = score(task, lang, native.translate(expr, lang), work / lang)
                if cases["reference"]["wrong"] or not cases["mutant"]["wrong"]:
                    raise ValueError(("Sealed oracle calibration failed", key, cases))
                receipt["calibration"][key] = cases
        receipt["calibration_seconds"] = monotonic() - start
        for row in trials:
            started = monotonic()
            result = None
            if row["decision"] == "accept":
                result = score(by_name[row["task"]], row["language"], row["selected"], work / row["language"])
            receipt["trials"][row["trial"]] = dict(score=result, seconds=monotonic()-started)
    (output / "scores.json").write_text(json.dumps(receipt, separators=(",", ":")) + "\n")
    subprocess.run([sys.executable, "-B", HERE / "report.py", output], check=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("output", type=Path)
    main(p.parse_args().output)
