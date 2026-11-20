"""Report matched maintenance trials, with a direct comparison to the 20% target."""

import argparse
from collections import Counter
import json
import math
from pathlib import Path
import re
import sys

# Read the earlier report and statistics helpers explicitly. This CLI has the
# same filename and the local run.py has the same name as the original runner.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "iterate"))
from report import BOOTSTRAP_DRAWS, Trial, paired, pretty, rate, repair_cost, table

CONDITIONS = ("gpp_context", "python_context", "rust_context", "gpp_target", "gpp_projected")
MATCHES = (
    ("gpp_context", "python_context"), ("gpp_context", "rust_context"),
    ("gpp_context", "gpp_target"), ("gpp_projected", "python_context"),
    ("gpp_projected", "rust_context"),
)
LABELS = {
    "gpp_context": "GPT++ with caller context",
    "python_context": "Typed Python with caller context",
    "rust_context": "Rust with caller context",
    "gpp_target": "GPT++ target only",
    "gpp_projected": "GPT++ from Python syntax with caller context",
}
TARGET = re.compile(r"^(?:pub )?(?:fn|def) ([A-Za-z_][A-Za-z_0-9]*)\(", re.MULTILINE)
MISMATCH = re.compile(r"^([A-Za-z_][A-Za-z_0-9]*)\(.*\) returned ")
SCOPE_ERRORS = ("editable function boundary", "outside the function", "different scope",
                "additional statement", "exactly one expression", "unclosed delimiter")


def load(path):
    with path.open(encoding="utf-8") as stream:
        meta, *rows = map(json.loads, stream)
    tasks = meta["tasks"]
    if (meta["study"] != "multi-caller-maintenance-v5" or meta["conditions"] != list(CONDITIONS)
            or len(set(tasks)) != 8 or len(tasks) != 8 or len(meta["models"]) != 1 or meta["seeds"] != [42]
            or meta["primary_comparator"] != "python_context"):
        raise ValueError("Unexpected maintenance study manifest.")
    assigned = {(meta["models"][0], 42, task, condition) for task in tasks for condition in CONDITIONS}
    records = {}
    for row in rows:
        t = Trial.parse(row)
        condition = row["condition"]
        key = t.model, t.seed, t.task, condition
        if key not in assigned or key in records or condition.split("_")[0] != t.language:
            raise ValueError(f"Unexpected assignment {key}.")
        if (len(t.outcomes) not in (1, 2) or t.accepted != (t.outcomes[-1] == "accepted")
                or t.first != (t.accepted and len(t.outcomes) == 1)):
            raise ValueError(f"Inconsistent verdicts for {key}.")
        records[key] = t
    if len(records) != len(assigned):
        raise ValueError(f"Only {len(records)}/{len(assigned)} trials are complete.")
    return meta, rows, records


def counts(records, condition):
    trials = [t for key, t in records.items() if key[3] == condition]
    return len(trials), sum(t.accepted for t in trials), sum(t.tokens for t in trials)


def target_table(records):
    metrics = []
    for left, right in [m for m in MATCHES if m[1] != "gpp_target"]:
        total, successes, tokens = counts(records, left)
        _, baseline_successes, baseline_tokens = counts(records, right)
        if baseline_successes:
            target = 0.80 * baseline_tokens / baseline_successes
            ratio = tokens / successes / (baseline_tokens / baseline_successes) if successes else None
            reduction = (max(0.0, 1 - target * successes / tokens) * 100
                         if successes and tokens else None)
            minimum = max(math.ceil(tokens / target), math.ceil(baseline_successes - 0.02 * total))
            min_text = str(minimum) if minimum <= total else f"{minimum} required with {total} assigned"
            target_text = pretty(target)
        else:
            ratio = reduction = None
            target_text = min_text = "undefined"
        metrics.append((left, right, target_text, pretty(ratio, 3),
                        pretty(100 * (ratio - 0.80) if ratio is not None else None, 1),
                        pretty(reduction, 1), min_text))
    print("\n## Distance to the 20% target")
    print("\nThese are observed point estimates. The last column keeps token spending fixed "
          "and applies both the token target and the acceptance margin to the observed comparator.")
    table(["GPT++ workflow", "Comparator", "Target tokens/accepted", "Observed cost ratio",
           "Gap above target (pp of baseline)", "Required token cut at observed acceptance (%)",
           "Minimum accepts at observed spending"], metrics)


def render(path):
    meta, rows, records = load(path)
    tasks = meta["tasks"]
    print("# Multi-caller maintenance benchmark")
    print(f"\nAll {len(rows)} trials completed across {len(tasks)} task families and five conditions "
          f"on {meta['models'][0]}. The {meta['public_cases']} public and {meta['hidden_cases']} hidden "
          "cases exercised both the edited targets and unchanged callers.")
    print("\nAn accepted change passes the checker and both test groups. Reported tokens include "
          "the rendered model input, generated output, failed attempts and repairs. Workflow "
          "time includes model calls and public checks. Held-out scoring time is recorded separately.")
    print("\n## Matched workflows")
    table(["Condition", "Workflow"], LABELS.items())
    by_arm = {condition: [t for key, t in records.items() if key[3] == condition]
              for condition in CONDITIONS}
    table(["Condition", "Calls", "First accepted", "Accepted", "Input tokens", "Output tokens",
           "Total tokens", "Tokens/accepted", "Workflow s/accepted"], [
        (condition, sum(len(t.outcomes) for t in group), rate(sum(t.first for t in group), len(group)),
         rate(accepted, len(group)), sum(t.inputs for t in group), sum(t.outputs for t in group),
         tokens, pretty(tokens / accepted if accepted else None),
         pretty(sum(t.wall_ms for t in group) / 1000 / accepted if accepted else None))
        for condition, group in by_arm.items() for _, accepted, tokens in [counts(records, condition)]
    ])
    print("\n## Paired estimates")
    print(f"\nBrackets are 95% percentile intervals from {BOOTSTRAP_DRAWS:,} task resamples. "
          "The acceptance interval must start at −2 percentage points or higher and the "
          "tokens-per-accepted interval must end at 0.80 or lower to meet both criteria.")
    table(["Numerator", "Comparator", "Matched", "Tasks", "Acceptance Δ (pp)",
           "All-token ratio", "Tokens/accepted ratio", "Workflow s/accepted ratio", "Thresholds"],
          [(left, *paired(records, right, len(tasks), numerator=left, include_raw=True))
           for left, right in MATCHES])
    target_table(records)
    repair_cost(path, CONDITIONS)

    print("\n## Outcomes by task")
    entries = {(t["task"], t["condition"]): t["attempts"][-1]["outcome"] for t in rows}
    table(["Task", *CONDITIONS], [(task, *(entries[task, arm] for arm in CONDITIONS)) for task in tasks])
    print("\n## Failure diagnostics")
    outcomes = Counter()
    locations = Counter()
    boundaries = Counter()
    for row in rows:
        arm = row["condition"]
        for attempt in row["attempts"]:
            if attempt["stage"] == "patch" and any(hint in attempt["public_detail"].lower()
                                                    for hint in SCOPE_ERRORS):
                boundaries[arm] += 1
        if not row["accepted"]:
            last = row["attempts"][-1]
            heldout = last["outcome"].startswith("heldout_")
            stage = "held-out" if heldout else last["stage"]
            outcomes[arm, stage, last["outcome"]] += 1
            text = row["heldout_detail"] if heldout else last["public_detail"]
            mismatch = MISMATCH.match(text)
            target = TARGET.search(last["prompt"])
            if mismatch and target:
                where = "target" if mismatch[1] == target[1] else "caller"
                locations[arm, stage, where] += 1
    table(["Condition", "Stage", "Result", "Count"],
          [(*key, count) for key, count in sorted(outcomes.items())])
    print("\nWrong-output diagnostics identify the first failing call in the tested group.")
    table(["Condition", "Stage", "First failing entry", "Terminal trials"],
          [(*key, count) for key, count in sorted(locations.items())])
    table(["Condition", "Attempts with an explicit output-boundary error"],
          [(arm, boundaries[arm]) for arm in CONDITIONS])

    print("\n## Change provenance")
    for task in tasks:
        item = meta["sources"][task]
        print(f"\n- **{task}**. {item['provenance']} [Primary source]({item['source_url']})")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("log", type=Path)
    try:
        render(cli.parse_args().log)
    except (ValueError, OSError, KeyError) as exc:
        cli.exit(1, f"{exc}\n")
