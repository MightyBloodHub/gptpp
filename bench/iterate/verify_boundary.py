"""Audit the v4 manifest, per-call settings, judgments, and reported point estimates.

Add --replay with the study Python environment to rescore every completion in
the frozen evaluation sandbox. --tokenizer accepts Qwen's tokenizer.json from
Qwen2.5-Coder-7B-Instruct revision c03e6d358207e414f1eca0bb1891e29f1db0e242
and requires the tokenizers package. All verification is offline.
"""

import argparse
from collections import Counter
from contextlib import redirect_stdout
from hashlib import sha256
from io import StringIO
import json
import math
from pathlib import Path
import random
import sys

import report_boundary as reporting
import run_boundary as study
from boundary_tasks import TASKS
from verify import PUBLIC_OUTCOMES, file_digest, require


# Captured from the task corpus and the local model manifest before inference.
CORPUS_SHA = "13b519cd9b7060c0c9a858420d9c94b060818a239631140f1451fbe33443b7d8"
MODEL_SHA = "dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364"
TEMPLATE_SHA = "1e65450c30670713aa47fe23e8b9662bdf4065e81cc8e3cbfaa98924fcc0d320"
TOKENIZER_SHA = "c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539"


def check_manifest(meta):
    require(meta["study"] == "scalar-boundary-stop-v4", "wrong study")
    require(meta["models"] == [study.MODEL] and meta["seeds"] == [42], "model/seed roster drift")
    require(meta["model_digests"] == {study.MODEL: MODEL_SHA}, "model manifest digest drift")
    require(sha256(meta["model_template"].encode()).hexdigest() == TEMPLATE_SHA, "model template drift")
    # The pinned model manifest has no parameters layer setting custom stops.
    require(meta["default_stops"] == [] and meta["boundary_stops"] == study.STOPS, "stop settings drift")
    require(meta["conditions"] == list(study.ARMS) and tuple(study.ARMS) == reporting.CONDITIONS,
            "condition roster drift")
    options = {"seed": 42, "temperature": 0, "num_ctx": 2048, "num_predict": 240}
    require(meta["model_options"] == options, "initial sampling settings drift")
    require(meta["repair_options"] == {**options, "seed": 43, "temperature": 0.25}, "repair settings drift")
    require(meta["order_seed"] == 7307 and meta["max_attempts"] == 2, "order seed or call budget drift")
    corpus = json.dumps(TASKS, sort_keys=True, separators=(",", ":")).encode()
    require(sha256(corpus).hexdigest() == meta["corpus_sha256"] == CORPUS_SHA, "task corpus drift")
    require(meta["tasks"] == [t["id"] for t in TASKS], "task roster drift")
    require(meta["task_kinds"] == {t["id"]: t["kind"] for t in TASKS}, "task kinds drift")
    counts = tuple(sum(len(t[group]) for t in TASKS) for group in ("public", "heldout"))
    require(counts == (meta["public_total"], meta["holdout_total"]), "oracle size drift")
    require(meta["validated_reference_results"] == 3 * sum(counts), "reference preflight count differs")
    root = study.pilot.ROOT
    dependencies = [*root.glob("src/*"), *root.glob("spec/*"),
                    *(study.HERE / f for f in ("tasks.py", "boundary_tasks.py", "fragments.py", "run_study.py",
                                              "run_infill.py", "run_boundary.py", "boundary-protocol.md")),
                    *(root / "tools" / f for f in ("scalar_fragment.py", "scalar_builtins.py")),
                    *(study.HERE.parent / "empirical" / f for f in ("run.py", "evaluate.py"))]
    require(meta["file_sha256"] == {str(p.relative_to(root)): file_digest(p) for p in dependencies if p.is_file()},
            "source fingerprint roster differs")
    require(file_digest(root / "target/debug/gpp") == meta["gpp_sha256"], "compiler fingerprint differs")
    rng = random.Random(meta["order_seed"])
    tasks = list(TASKS)
    rng.shuffle(tasks)
    order = []
    for task in tasks:
        arms = list(meta["conditions"])
        rng.shuffle(arms)
        order.extend((task["id"], arm) for arm in arms)
    return order


def replay(tools, row, task, attempt):
    public, detail, code = study.materialize(tools, task, row["condition"], attempt["response"])
    if public == "pass":
        public, detail = tools.evaluate(task, row["language"], code, task["public"])
    require(public == attempt["public_outcome"], f"replayed public result {public} differs")
    differences = int(detail != attempt["public_detail"])
    if public == "pass":
        outcome, detail = tools.evaluate(task, row["language"], code, task["heldout"], heldout=True)
        terminal = "accepted" if outcome == "pass" else "heldout_" + outcome
        require(terminal == attempt["outcome"], f"replayed held-out result {terminal} differs")
        differences += int(detail != row["heldout_detail"])
    return differences


def check_trial(row, meta, task, tools):
    arm = row["condition"]
    target = arm.split("_")[0]
    surface = "python" if arm == "gpp_projected_stop" else target
    template = "gpp_projected" if arm == "gpp_projected_stop" else target + "_fim"
    require((row["kind"], row["form"]) == (task["kind"], task["form"]), "task labels drift")
    attempts = row["attempts"]
    previous = feedback = None
    differences = 0
    for i, a in enumerate(attempts):
        expected = dict(meta["repair_options" if i else "model_options"])
        if arm.endswith("_stop"):
            expected["stop"] = list(dict.fromkeys(meta["default_stops"] + meta["boundary_stops"][surface]))
        require(a["sampling"] == expected, "recorded sampling/stop configuration differs")
        prefix, suffix = study.fim.infill_context(task, template, previous, feedback)
        require((a["prompt"], a["suffix"]) == (prefix, suffix), "public prompt/suffix differs")
        require(isinstance(a["response"], str), "missing completion")
        for key, limit in (("input_tokens", "num_ctx"), ("output_tokens", "num_predict")):
            require(type(a[key]) is int and 0 < a[key] <= expected[limit], f"{key} outside configured limit")
        require(a["done_reason"] in ("stop", "length"), "unexpected termination")
        if a["done_reason"] == "length":
            require(a["output_tokens"] == expected["num_predict"], "output cap disagrees with termination")
        for field in ("model_ms", "tool_ms", "prompt_eval_ms", "generation_ms", "load_ms"):
            require(type(a[field]) in (int, float) and math.isfinite(a[field]) and a[field] >= 0,
                    f"invalid {field}")
        public, outcome = a["public_outcome"], a["outcome"]
        require(public in PUBLIC_OUTCOMES, "unknown public verdict")
        if public == "pass":
            require(i == len(attempts) - 1 and outcome in {
                "accepted", *("heldout_" + o for o in PUBLIC_OUTCOMES - {"pass"})}, "invalid hidden verdict")
        else:
            require(outcome == public, "public failure relabeled")
        if tools is not None:
            differences += replay(tools, row, task, a)
        previous = a["response"]
        feedback = study.repair_feedback(task, surface, a["public_detail"])
    if attempts[-1]["public_outcome"] != "pass":
        require(len(attempts) == 2 and row["heldout_ms"] == 0 and not row["heldout_detail"],
                "missing repair or spurious hidden score")
    measured = sum(a["model_ms"] + a["tool_ms"] for a in attempts)
    require(row["wall_ms"] + .01 >= measured, "workflow interval shorter than calls")
    return differences


def audit_report(log, rows, meta, assigned, records, hidden, report_path):
    sink = StringIO()
    with redirect_stdout(sink):
        reporting.report(meta, assigned, records, hidden)
        reporting.repair_cost(log, reporting.CONDITIONS)
    rendered = sink.getvalue()
    digest = file_digest(log)
    if report_path is not None:
        require(rendered.rstrip() in report_path.read_text(encoding="utf-8"),
                "archived Markdown differs from current reporter")
    totals = {}
    for arm in study.ARMS:
        trials = [r for r in rows if r["condition"] == arm]
        calls = [a for r in trials for a in r["attempts"]]
        inputs = sum(a["input_tokens"] for a in calls)
        outputs = sum(a["output_tokens"] for a in calls)
        wins = sum(r["accepted"] for r in trials)
        first = sum(r["first_accepted"] for r in trials)
        durations = [sum(r[key] for r in trials) / 1000 for key in ("wall_ms", "heldout_ms")]
        point = inputs + outputs
        got = [arm, "8/8", len(calls), reporting.rate(first, 8), reporting.rate(wins, 8),
               inputs, outputs, point, reporting.pretty(point / wins if wins else None),
               reporting.pretty(sum(a["model_ms"] for a in calls) / 1000),
               reporting.pretty(sum(a["tool_ms"] for a in calls) / 1000),
               *map(reporting.pretty, durations), reporting.pretty(durations[0] / wins if wins else None),
               reporting.pretty(sum(durations) / wins if wins else None)]
        require("| " + " | ".join(map(str, got)) + " |" in rendered, f"report totals differ for {arm}")
        totals[arm] = (wins, point, durations[0])
        initial = sum(r["attempts"][0]["input_tokens"] + r["attempts"][0]["output_tokens"] for r in trials)
        repair = [arm, initial, first, reporting.pretty(initial / first if first else None),
                  len(calls) - 8, point - initial, wins - first]
        require("| " + " | ".join(map(str, repair)) + " |" in rendered, f"repair totals differ for {arm}")
    for left, right in reporting.COMPARISONS:
        lw, lt, ls = totals[left]
        rw, rt, rs = totals[right]
        points = (100 * (lw - rw) / 8, lt / rt, lt * rw / (lw * rt) if lw and rw else None,
                  ls * rw / (lw * rs) if lw and rw and rs else None)
        match = next(line for line in rendered.splitlines() if line.startswith(f"| {left} | {right} |"))
        cells = [c.strip() for c in match.strip("|").split("|")]
        require(cells[2:4] == ["8/8", "8"] and [c.split()[0] for c in cells[4:8]]
                == [reporting.pretty(x, 4) for x in points], f"paired report differs for {left}/{right}")
    return digest


def verify_input_tokens(path, calls, template):
    try:
        from tokenizers import Tokenizer
    except ImportError as exc:
        raise ValueError("--tokenizer requires the tokenizers package") from exc
    require(file_digest(path) == TOKENIZER_SHA, "independent tokenizer fingerprint differs")
    require(template.startswith("{{- if .Suffix }}<|fim_prefix|>{{ .Prompt }}<|fim_suffix|>{{ .Suffix }}<|fim_middle|>"),
            "unrecognized FIM template")
    encoder = Tokenizer.from_file(str(path))
    for idx, a in enumerate(calls, 1):
        prompt = f"<|fim_prefix|>{a['prompt']}<|fim_suffix|>{a['suffix']}<|fim_middle|>"
        require(len(encoder.encode(prompt).ids) == a["input_tokens"], f"call {idx}: prompt token count differs")
    print(f"Independently retokenized all {len(calls)} rendered FIM inputs.")


def verify(log, replay_enabled, report_path, tokenizer_path=None):
    original_sha = file_digest(log)
    meta, assigned, records, hidden = reporting.load(log)
    rows = [json.loads(line) for line in log.read_text().splitlines() if line.strip()][1:]
    require([(r["task"], r["condition"]) for r in rows] == check_manifest(meta), "assignment order/coverage drift")
    tools = None
    if replay_enabled:
        tools = study.Tools(study.pilot.ROOT, study.pilot.ROOT / "target/debug/gpp")
        tools.canaries()
    tasks = {t["id"]: t for t in TASKS}
    differences = 0
    for row in rows:
        try:
            differences += check_trial(row, meta, tasks[row["task"]], tools)
        except (ValueError, KeyError, TypeError) as err:
            raise ValueError(f"{row['task']}/{row['condition']}: {err}") from err
    final_sha = audit_report(log, rows, meta, assigned, records, hidden, report_path)
    require(original_sha == final_sha, "log changed during verification")
    calls = [a for r in rows for a in r["attempts"]]
    if tokenizer_path is not None:
        verify_input_tokens(tokenizer_path, calls, meta["model_template"])
    print(f"Verified {len(rows)} trials, {len(calls)} model calls and {sum(r['accepted'] for r in rows)} accepted trials.")
    print(f"Reported tokens: {sum(a['input_tokens'] for a in calls)} input, {sum(a['output_tokens'] for a in calls)} output.")
    print(f"Generation terminations: {dict(Counter(a['done_reason'] for a in calls))}.")
    if replay_enabled:
        print(f"Replayed {len(calls)} public verdicts and {sum(a['public_outcome'] == 'pass' for a in calls)} "
              f"held-out verdicts; {differences} diagnostic text differences.")
    print(f"Log SHA-256: {final_sha}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    parser.add_argument("--report", type=Path, help="also check the archived Markdown against a fresh rendering")
    parser.add_argument("--tokenizer", type=Path, help="verify every rendered input with the pinned Qwen tokenizer JSON")
    parser.add_argument("--replay", action="store_true", help="rescore the archived completions")
    args = parser.parse_args()
    try:
        verify(args.log, args.replay, args.report, args.tokenizer)
    except (ValueError, KeyError, OSError, TypeError) as error:
        sys.exit(str(error))
