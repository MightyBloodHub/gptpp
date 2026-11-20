"""Summarize the caller-context experiment and the distance to 20% savings."""

import argparse
import json
import math
from pathlib import Path

from run_adaptive import CONDITIONS, PRIMARY, STUDY, use_callers
from report import BOOTSTRAP_DRAWS, Trial, paired, pretty, rate, table

BASELINES = (PRIMARY, "rust_adaptive")
CONTROL_ARMS = ("gpp_target", "gpp_context")
NAMES = {
    "gpp_adaptive": "GPT++ adaptive",
    "python_adaptive": "Typed Python adaptive",
    "rust_adaptive": "Rust adaptive",
    "gpp_target": "GPT++ target only",
    "gpp_context": "GPT++ caller context always",
}


def read_log(path):
    with path.open(encoding="utf-8") as stream:
        meta, *rows = map(json.loads, stream)
    if (meta["study"] != STUDY or meta["conditions"] != list(CONDITIONS)
            or meta["primary_comparator"] != PRIMARY or len(set(meta["tasks"])) != 8
            or len(meta["tasks"]) != 8 or len(meta["models"]) != 1 or meta["seeds"] != [42]):
        raise ValueError("Unexpected adaptive maintenance manifest.")
    assigned = {(meta["models"][0], 42, task, condition)
                for task in meta["tasks"] for condition in CONDITIONS}
    records = {}
    for row in rows:
        trial = Trial.parse(row)
        arm = row["condition"]
        key = trial.model, trial.seed, trial.task, arm
        if key not in assigned or key in records or arm.split("_")[0] != trial.language:
            raise ValueError(f"Unexpected assignment {key}.")
        if (len(trial.outcomes) not in (1, 2) or trial.accepted != (trial.outcomes[-1] == "accepted")
                or trial.first != (trial.accepted and len(trial.outcomes) == 1)):
            raise ValueError(f"Inconsistent attempt history for {key}.")
        entry = None
        for attempt in row["attempts"]:
            if attempt["caller_context"] != use_callers(arm, meta["targets"][trial.task], entry):
                raise ValueError(f"Caller-context rule violated for {key}.")
            entry = attempt["public_failed_entry"]
        records[key] = trial
    if len(records) != len(assigned):
        raise ValueError(f"Completed {len(records)}/{len(assigned)} assignments.")
    return meta, rows, records


def totals(records, arm):
    group = [trial for key, trial in records.items() if key[3] == arm]
    return len(group), sum(trial.accepted for trial in group), sum(trial.tokens for trial in group)


def distance(records, baseline):
    count, successes, tokens = totals(records, "gpp_adaptive")
    _, b_successes, b_tokens = totals(records, baseline)
    acceptance_points = 100 * (successes - b_successes) / count
    if b_successes == 0 or b_tokens == 0:
        return NAMES[baseline], *(["undefined"] * 3), pretty(acceptance_points, 1), "undefined", "undefined"
    baseline_cost = b_tokens / b_successes
    target_cost = 0.80 * baseline_cost
    ratio = tokens / successes / baseline_cost if successes else None
    gap = 100 * (ratio - 0.80) if ratio is not None else None
    token_cut = max(0.0, 100 * (1 - target_cost * successes / tokens)) if successes and tokens else None
    required = max(math.ceil(tokens / target_cost), math.ceil(b_successes - 0.02 * count))
    minimum = str(required) if required <= count else f"{required} required with {count} assigned"
    return (NAMES[baseline], pretty(target_cost), pretty(ratio, 3), pretty(gap, 1),
            pretty(acceptance_points, 1), pretty(token_cut, 1), minimum)


def report(path):
    meta, rows, records = read_log(path)
    print("# Adaptive caller-context benchmark")
    print(f"\n{len(rows)} matched trials on {len(meta['tasks'])} new tasks with {meta['models'][0]}. "
          f"The harness scored {meta['public_cases']} public and {meta['hidden_cases']} withheld cases. "
          "An accepted patch must pass both. The token budget counts the full input and generated output "
          "of every call, including unsuccessful calls and repairs.")
    print("\n## Acceptance and usage")
    table(["Workflow", "Calls", "First accepted", "Accepted", "Input tokens", "Output tokens",
           "Total tokens", "Tokens/accepted", "Workflow seconds/accepted"], [
        (NAMES[arm], sum(len(t.outcomes) for t in group), rate(sum(t.first for t in group), count),
         rate(accepted, count), sum(t.inputs for t in group), sum(t.outputs for t in group),
         tokens, pretty(tokens / accepted if accepted else None),
         pretty(sum(t.wall_ms for t in group) / 1000 / accepted if accepted else None))
        for arm in CONDITIONS
        for group in [[t for key, t in records.items() if key[3] == arm]]
        for count, accepted, tokens in [totals(records, arm)]
    ])
    print("\n## Retry behavior")
    retry_rows = []
    for arm in CONDITIONS:
        group = [r for r in rows if r["condition"] == arm]
        retries = [r for r in group if len(r["attempts"]) == 2]
        caller_failures = [r for r in retries
                           if r["attempts"][0]["public_failed_entry"] not in (None, r["target"])]
        with_context = [r for r in retries if r["attempts"][1]["caller_context"]]
        without_context = [r for r in retries if not r["attempts"][1]["caller_context"]]
        retry_rows.append((NAMES[arm], len(retries), len(caller_failures), len(with_context),
                           sum(r["accepted"] for r in with_context),
                           sum(r["accepted"] for r in without_context),
                           sum(r["attempts"][1]["input_tokens"] + r["attempts"][1]["output_tokens"] for r in retries)))
    table(["Workflow", "Retries", "First public failure at caller", "Retries with excerpts",
           "Accepted with excerpts on retry", "Accepted without excerpts on retry", "Retry tokens"], retry_rows)
    print("\n## Paired estimates")
    print(f"\nBrackets are 95% percentile intervals from {BOOTSTRAP_DRAWS:,} task-cluster resamples. "
          "The lower acceptance bound must be at least −2 percentage points. The upper cost-ratio "
          "bound must be at most 0.80. Workflow time covers inference and public checks.")
    table(["Comparator", "Matched", "Tasks", "Acceptance Δ (pp)", "Total token ratio",
           "Tokens/accepted ratio", "Workflow time/accepted ratio", "Thresholds"],
          [paired(records, baseline, len(meta["tasks"]), numerator="gpp_adaptive", include_raw=True)
           for baseline in (*BASELINES, *CONTROL_ARMS)])
    print("\n## Distance to the 20% goal")
    print("\nThe table uses observed point estimates against the same adaptive policy. "
          "The required token reduction keeps GPT++ acceptance fixed. Required accepts keep GPT++ "
          "token spending fixed and apply both point targets.")
    table(["Comparator", "20% target tokens/accepted", "Observed GPT++ cost ratio",
           "Gap above 0.80 (pp of comparator)", "Acceptance Δ (pp)", "Further token cut (%)",
           "Accepted edits required at observed spending"], [distance(records, baseline) for baseline in BASELINES])
    print("\n## Task outcomes")
    lookup = {(row["task"], row["condition"]): row for row in rows}
    table(["Task", *CONDITIONS], [(task, *(lookup[task, arm]["attempts"][-1]["outcome"] for arm in CONDITIONS))
                                   for task in meta["tasks"]])
    print("\n## Same initial prompt in GPT++")
    print("\nThe adaptive and target-only arms start with identical prompt and sampling settings. "
          "The table shows tasks that triggered excerpts in the adaptive arm. A changed first reply "
          "can contribute to a changed final result.")
    comparisons = []
    for task in meta["tasks"]:
        adaptive, target = [lookup[task, arm] for arm in ("gpp_adaptive", "gpp_target")]
        attempts = adaptive["attempts"]
        if len(attempts) == 2 and attempts[1]["caller_context"]:
            comparisons.append((task, attempts[0]["public_failed_entry"],
                                "yes" if attempts[0]["response"] == target["attempts"][0]["response"] else "no",
                                attempts[-1]["outcome"], target["attempts"][-1]["outcome"]))
    if comparisons:
        table(["Task", "Caller that triggered context", "Same initial reply",
               "Adaptive final outcome", "Target-only final outcome"], comparisons)
    else:
        print("\nNo GPT++ public caller failure triggered excerpts.")
    print("\n## Change provenance")
    for task in meta["tasks"]:
        source = meta["sources"][task]
        print(f"\n- **{task}**. {source['provenance']} [Primary source]({source['source_url']})")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("log", type=Path)
    try:
        report(cli.parse_args().log)
    except (ValueError, OSError, KeyError) as exc:
        cli.exit(1, f"{exc}\n")
