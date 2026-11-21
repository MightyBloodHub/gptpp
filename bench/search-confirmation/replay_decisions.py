"""Replay three publication policies on the original eleven exercises, without inference."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from corpus import TASKS


HERE = Path(__file__).resolve().parent
BASELINE = "0ad5a404b0f9108a3a5786325782eee663c57f43"
ARCHIVE_SHA256 = "1f8df6b2cb030cf6856c43b6ca3a635913e71d659aac3cad184762856163e158"
QWEN = "qwen2.5-coder:7b"
POLICIES = ("piecewise", "qwen", "piecewise_then_qwen")


def archived_rows():
    data = (HERE / "results.jsonl").read_bytes()
    if sha256(data).hexdigest() != ARCHIVE_SHA256:
        raise ValueError("The archive differs from commit " + BASELINE)
    rows = {}
    for line in data.splitlines():
        row = json.loads(line)
        if "key" in row:
            key = row["kind"], row["key"]
            if key in rows:
                raise ValueError(f"Duplicate archive decision {key}")
            rows[key] = row
    return rows


def outcome(row):
    score = row["score"]
    if row["public_status"] != "pass":
        if score is not None:
            raise ValueError("Found a scored public failure for " + row["key"])
        return "abstained"
    return "wrong" if score["direct_wrong"] or score["history_wrong"] else "correct"


def replay():
    rows = archived_rows()
    decisions = []
    counts = {p: Counter(correct=0, wrong=0, abstained=0) for p in POLICIES}
    usage = {p: dict(calls=0, input_tokens=0, output_tokens=0) for p in POLICIES}
    for task in TASKS:
        key = f"{QWEN}/{task.name}/gpp"
        native = rows["native", f"piecewise/{task.name}"]
        model = rows["trial", key]
        reply = rows["call", key]["reply"]
        # This is the whole routing rule. Only score the chosen output afterwards.
        published = native["expression"] is not None and native["public_status"] == "pass"
        source = "piecewise" if published else "qwen"
        decision = {"task": task.name, "source": source, "search_status": native["report"]["status"]}
        for policy, selected in zip(POLICIES, (native, model, native if published else model), strict=True):
            result = outcome(selected)
            if selected["accepted"] != (result == "correct"):
                raise ValueError("Score disagrees with archived acceptance for " + selected["key"])
            counts[policy][result] += 1
            decision[policy] = result
            if selected is model:
                usage[policy]["calls"] += 1
                usage[policy]["input_tokens"] += reply["prompt_eval_count"]
                usage[policy]["output_tokens"] += reply["eval_count"]
        decisions.append(decision)
    return {
        "kind": "archived_decision_replay",
        "baseline": BASELINE,
        "archive_sha256": ARCHIVE_SHA256,
        "new_model_calls": 0,
        "decisions": decisions,
        "counts": counts,
        "archived_model_usage": usage,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit the machine-readable replay")
    args = parser.parse_args()
    report = replay()
    if args.json:
        print(json.dumps(report, indent=2))
        return
    print(f"Archived decision replay at {BASELINE}. No new model calls.\n")
    print("| Exercise | Piecewise | Direct Qwen | Routed to | Routed outcome |")
    print("|---|---|---|---|---|")
    for row in report["decisions"]:
        print(f"| {row['task']} | {row['piecewise']} | {row['qwen']} | {row['source']} "
              f"| {row['piecewise_then_qwen']} |")
    print("\n| Policy | Correct / assigned | Wrong | Abstained | Archived calls | Input tokens | Output tokens |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    for policy in POLICIES:
        counts, usage = report["counts"][policy], report["archived_model_usage"][policy]
        print(f"| {policy} | {counts['correct']}/{len(report['decisions'])} | {counts['wrong']} "
              f"| {counts['abstained']} | {usage['calls']} | {usage['input_tokens']} | {usage['output_tokens']} |")


if __name__ == "__main__":
    main()
