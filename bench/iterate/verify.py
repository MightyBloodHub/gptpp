"""Verify a locked v2/v3 trial roster, prompt reconstruction and token accounting.

Pass --replay with the benchmark's Python environment to rescore the logged
model output in the same sandbox without requesting any new model completions.
"""

import argparse
from collections import Counter
from hashlib import sha256
import json
import math
from pathlib import Path
import random
import re
import sys

import run_study as chat
import run_infill as fim
import report
from tasks import TASKS as PAIRED_TASKS
from replication_tasks import TASKS as INFILL_TASKS


# Captured before the first model run on each task set. These hashes include
# all public and held-out cases, the starters and the three language references.
STUDIES = {
    "scalar-fragment-pilot-v2": (PAIRED_TASKS, chat.CONDITIONS, chat.pilot.MODELS, chat.ORDER_SEED,
                                "916189357a832ca914fbf0eea289dd637fe58c664883f657b898bb3d75f1195a"),
    "scalar-infill-replication-v3": (INFILL_TASKS, fim.CONDITIONS, (fim.MODEL,), fim.ORDER_SEED,
                                    "5cf96f0487518ebaf3c15c0879727aace097ea14aea65b7392e71733cba70281"),
}
PUBLIC_OUTCOMES = {"pass", "wrong_answer", "check_error", "runtime_error"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def file_digest(path):
    return sha256(path.read_bytes()).hexdigest()


def manifest_checks(meta):
    study = meta["study"]
    tasks, conditions, models, order_seed, locked_digest = STUDIES[study]
    root = chat.pilot.ROOT
    require(meta["type"] == "metadata", "expected leading run manifest")
    require(meta["conditions"] == list(conditions) and meta["models"] == list(models), "condition/model roster drift")
    require(meta["tasks"] == [t["id"] for t in tasks] and meta["seeds"] == [42], "task/seed roster drift")
    require(meta["order_seed"] == order_seed and meta["max_attempts"] == 2, "order seed or call budget drift")
    require(meta["model_options"] == chat.pilot.OPTIONS, "recorded model options differ")
    digests = meta["model_digests"]
    require(set(digests) == set(models) and all(re.fullmatch(r"[0-9a-f]{64}", d) for d in digests.values()),
            "malformed model digest roster")
    corpus = json.dumps(tasks, sort_keys=True, separators=(",", ":")).encode()
    require(sha256(corpus).hexdigest() == locked_digest, "corpus differs from its frozen digest")
    public = sum(len(t["public"]) for t in tasks)
    heldout = sum(len(t["heldout"]) for t in tasks)
    require((meta["public_total"], meta["holdout_total"]) == (public, heldout), "case totals differ")
    require(meta["validated_reference_results"] == 3 * (public + heldout), "reference check count differs")
    require(meta["file_sha256"], "missing source digests")
    for name, expected in meta["file_sha256"].items():
        path = (root / name).resolve()
        require(path.is_relative_to(root) and file_digest(path) == expected, f"source digest mismatch ({name})")
    require(file_digest(root / "target/debug/gpp") == meta["gpp_sha256"], "local compiler differs from recorded binary")
    if study.endswith("v3"):
        require((meta["primary"], meta["secondary"]) == ("gpp_fim", "gpp_projected"), "analysis arm drift")
        # The replication imports wrappers from the v2 task file. v3 did not
        # list this transitive dependency, so compare it with the locked v2 hash.
        require(file_digest(chat.HERE / "tasks.py") ==
                "23254d59e987a4565613c38b780a30b18c2eff5883f49f58c79b11a86ace5468",
                "shared task wrapper differs from its frozen v2 version")

    order = []
    rng = random.Random(order_seed)
    for model in models:
        task_order = tasks.copy()
        rng.shuffle(task_order)
        for t in task_order:
            arm_order = list(conditions)
            rng.shuffle(arm_order)
            order.extend((model, t["id"], arm) for arm in arm_order)
    return {t["id"]: t for t in tasks}, order


def check_prompt(task, row, index):
    arm = row["condition"]
    lang = row["language"]
    attempts = row["attempts"]
    prev = attempts[index - 1] if index else None
    current = attempts[index]
    if arm == "gpp_full":
        expected = chat.pilot.make_prompt(task, lang)
        if prev:
            code = chat.pilot.candidate(prev["response"])
            expected += ("\n\nYour previous function:\n" + code + "\n\nPublic evaluator feedback:\n"
                         + prev["public_detail"] + "\n\nReturn the complete corrected function only.")
    elif arm.endswith("_fragment") or arm == "gpp_chat":
        expected = chat.prompt_for(task, lang)
        require(current["assistant_prefix"] == chat.prefix(task, lang), "immutable assistant prefix differs")
        if prev:
            expected += ("\nPrevious completion:\n" + prev["response"] + "\nFeedback: "
                         + chat.repair_feedback(task, lang, prev["public_detail"])
                         + "\nChange the failed calculation or syntax and complete the function again.")
    else:
        feedback = chat.repair_feedback(task, lang, prev["public_detail"]) if prev else None
        expected, suffix = fim.infill_context(task, arm, prev["response"] if prev else None, feedback)
        require(current["suffix"] == suffix, "infill suffix differs")
    require(current["prompt"] == expected, "prompt differs from frozen public-only construction")


def replay_attempt(tools, task, row, attempt):
    arm = row["condition"]
    lang = row["language"]
    response = attempt["response"]
    if arm == "gpp_full":
        code = chat.pilot.candidate(response)
        public = "pass"
    elif arm.endswith("_fragment") or arm == "gpp_chat":
        public, _, code = chat.edited_function(tools, task, lang, response)
    else:
        public, _, code = fim.materialize(tools, task, arm, response)
    if public == "pass":
        public, _ = tools.evaluate(task, lang, code, task["public"])
    require(public == attempt["public_outcome"], f"public outcome replay gives {public}")
    if public == "pass":
        hidden, _ = tools.evaluate(task, lang, code, task["heldout"], heldout=True)
        result = "accepted" if hidden == "pass" else "heldout_" + hidden
        require(result == attempt["outcome"], f"held-out replay gives {result}")


def check_trial(row, task, options, tools):
    arm = row["condition"]
    require(row["language"] == arm.split("_")[0], "language disagrees with condition")
    require((row["kind"], row["form"]) == (task["kind"], task["form"]), "task labels differ")
    require(row["seed"] == options["seed"], "assignment seed differs")
    attempts = row["attempts"]
    require(1 <= len(attempts) <= 2, "expected one or two calls")
    for i, a in enumerate(attempts):
        require(type(a["response"]) is str, "missing raw model response")
        check_prompt(task, row, i)
        require(type(a["input_tokens"]) is int and 0 < a["input_tokens"] <= options["num_ctx"],
                "prompt count outside recorded context limit")
        require(type(a["output_tokens"]) is int and 0 < a["output_tokens"] <= options["num_predict"],
                "generation count outside recorded output cap")
        require(a["done_reason"] in ("stop", "length"), "unexpected generation termination")
        if a["done_reason"] == "length":
            require(a["output_tokens"] == options["num_predict"], "length stop disagrees with output cap")
        if arm != "gpp_full":
            expected = dict(options)
            if i:
                expected.update(temperature=0.25, seed=43)
            require(a["sampling"] == expected, "sampling options differ from frozen protocol")
        for metric in ("model_ms", "tool_ms", "load_ms", "prompt_eval_ms", "generation_ms"):
            require(type(a[metric]) in (int, float) and math.isfinite(a[metric]) and a[metric] >= 0,
                    f"invalid timing {metric}")
        public, result = a["public_outcome"], a["outcome"]
        require(public in PUBLIC_OUTCOMES, "invalid public outcome")
        if public == "pass":
            require(i == len(attempts) - 1 and
                    result in {"accepted", *("heldout_" + x for x in PUBLIC_OUTCOMES - {"pass"})},
                    "public pass missing its terminal oracle outcome")
        else:
            require(result == public, "public failure relabeled")
        if tools is not None:
            replay_attempt(tools, task, row, a)
    last = attempts[-1]
    require(last["public_outcome"] == "pass" or len(attempts) == 2, "missing public-feedback repair")
    require(row["accepted"] is (last["outcome"] == "accepted"), "acceptance flag disagrees with scoring")
    require(row["first_accepted"] is (row["accepted"] and len(attempts) == 1), "first acceptance flag differs")
    require(math.isfinite(row["wall_ms"]) and row["wall_ms"] + .01 >= sum(a["model_ms"] + a["tool_ms"] for a in attempts),
            "workflow time shorter than the model and tool calls")
    require(math.isfinite(row["heldout_ms"]) and row["heldout_ms"] >= 0, "invalid hidden scoring time")
    if last["public_outcome"] != "pass":
        require(row["heldout_ms"] == 0 and not row["heldout_detail"], "public failure reached hidden scorer")


def verify_report_points(path, meta, rows):
    """Cross-check the reported aggregate contrasts using the raw calls."""
    _, records, _ = report.load(path)
    totals = {}
    for arm in meta["conditions"]:
        trials = [r for r in rows if r["condition"] == arm]
        tokens = sum(a["input_tokens"] + a["output_tokens"] for r in trials for a in r["attempts"])
        totals[arm] = (len(trials), sum(r["accepted"] for r in trials), tokens, sum(r["wall_ms"] for r in trials))
    followup = meta["study"].endswith("v3")
    numerators = ("gpp_fim", "gpp_projected") if followup else ("gpp_fragment",)
    comparators = ("python_fim", "rust_fim", "gpp_chat") if followup else ("python_fragment", "rust_fragment", "gpp_full")
    for num in numerators:
        n, wins, tokens, elapsed = totals[num]
        for comp in comparators:
            m, baseline_wins, baseline_tokens, baseline_elapsed = totals[comp]
            require(n == m, "reported contrast has unequal assignment counts")
            expected = [100 * (wins - baseline_wins) / n]
            if followup:
                expected.append(tokens / baseline_tokens)
            for us, them in ((tokens, baseline_tokens), (elapsed, baseline_elapsed)):
                expected.append((us / wins) / (them / baseline_wins) if wins and baseline_wins and them else None)
            cells = report.paired(records, comp, n, num, include_raw=followup)
            require(cells[1] == f"{n}/{n}" and cells[2] == len(meta["tasks"]), "wrong report pair count")
            require([c.split(" ")[0] for c in cells[3:-1]] == [report.pretty(v, 4) for v in expected],
                    f"reported point estimate differs for {num} / {comp}")


def verify(path, replay):
    raw = path.read_bytes()
    lines = raw.decode().splitlines()
    require(lines, "empty log")
    meta, *rows = (json.loads(line) for line in lines)
    tasks, order = manifest_checks(meta)
    require([(r["model"], r["task"], r["condition"]) for r in rows] == order,
            f"expected {len(order)} completed assignments in seeded order; observed {len(rows)} records")
    tools = None
    if replay:
        tools = chat.Tools(chat.pilot.ROOT, chat.pilot.ROOT / "target/debug/gpp")
        tools.canaries()
    for row in rows:
        try:
            check_trial(row, tasks[row["task"]], meta["model_options"], tools)
        except (KeyError, TypeError, ValueError) as err:
            raise ValueError(f"{row['model']} / {row['task']} / {row['condition']}: {err}") from err
    verify_report_points(path, meta, rows)
    attempts = [a for r in rows for a in r["attempts"]]
    print(f"{path.name}: {len(rows)} trials; {len(attempts)} generation calls; {sum(r['accepted'] for r in rows)} accepted")
    print(f"Input tokens {sum(a['input_tokens'] for a in attempts)}; output tokens {sum(a['output_tokens'] for a in attempts)}; "
          f"maximum prompt {max(a['input_tokens'] for a in attempts)}; generation stops {dict(Counter(a['done_reason'] for a in attempts))}")
    print(f"SHA-256 {sha256(raw).hexdigest()}" + ("; public and held-out scores replayed" if replay else ""))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", nargs="+", type=Path)
    parser.add_argument("--replay", action="store_true", help="re-run model-produced source using the benchmark sandbox")
    args = parser.parse_args()
    try:
        for log in args.log:
            verify(log, args.replay)
    except (ValueError, KeyError, OSError, TypeError) as exc:
        sys.exit(str(exc))
