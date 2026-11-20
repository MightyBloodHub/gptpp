"""Report paired authoring conditions from a fragment pilot or replication JSONL log."""

import argparse
from collections import Counter, defaultdict
from itertools import product
import json
import math
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "empirical"))
from summarize import BOOTSTRAP_DRAWS, BOOTSTRAP_SEED, Trial, metrics, pretty, rate, safe, table


CONDITIONS = ("gpp_fragment", "gpp_full", "python_fragment", "rust_fragment")
REPLICATION = ("gpp_fim", "gpp_chat", "gpp_projected", "python_fim", "rust_fim")
REPLICATION_NUMERATORS = ("gpp_fim", "gpp_projected")
REPLICATION_COMPARATORS = ("python_fim", "rust_fim", "gpp_chat")


def load(path):
    manifest = None
    records = {}
    kinds = {}
    with path.open(encoding="utf-8") as data:
        for index, text in enumerate(data, 1):
            if not text.strip():
                continue
            try:
                row = json.loads(text)
                if not isinstance(row, dict):
                    raise ValueError("expected a JSON object")
                if row.get("type") == "metadata":
                    if records or manifest is not None:
                        raise ValueError("expected one leading manifest")
                    manifest = row
                    continue
                condition = row["condition"]
                if condition not in CONDITIONS and condition not in REPLICATION:
                    raise ValueError(f"unknown condition {condition}")
                trial = Trial.parse(row)
                if condition.split("_")[0] != trial.language:
                    raise ValueError(f"condition and language disagree for {condition}")
                if kinds.setdefault(trial.task, trial.kind) != trial.kind:
                    raise ValueError(f"inconsistent kind for {trial.task}")
                key = (trial.model, trial.seed, trial.task, condition)
                if key in records:
                    raise ValueError(f"duplicate trial {key}")
                records[key] = trial
            except (ValueError, KeyError, TypeError, OverflowError) as err:
                raise ValueError(f"{path}:{index}: {err}") from err
    if manifest is None:
        raise ValueError("a manifest with model, seed, task and condition rosters is required")
    for name, ty in (("models", str), ("seeds", int), ("tasks", str), ("conditions", str)):
        axis = manifest.get(name)
        if (not isinstance(axis, list) or not axis or any(type(x) is not ty for x in axis)
                or len(set(axis)) != len(axis)):
            raise ValueError(f"invalid manifest roster: {name}")
    if set(manifest["conditions"]) not in (set(CONDITIONS), set(REPLICATION)):
        raise ValueError("manifest must declare all four pilot or all five replication conditions")
    if "gpp_fim" in manifest["conditions"]:
        for role, numerator in zip(("primary", "secondary"), REPLICATION_NUMERATORS):
            if manifest.get(role, numerator) != numerator:
                raise ValueError(f"replication {role} numerator must be {numerator}")
    declared_kinds = manifest.get("task_kinds")
    if declared_kinds is not None:
        if (not isinstance(declared_kinds, dict) or set(declared_kinds) != set(manifest["tasks"])
                or any(k not in ("synthesis", "maintenance") for k in declared_kinds.values())
                or any(declared_kinds.get(task) != kind for task, kind in kinds.items())):
            raise ValueError("manifest task kinds must cover the roster and agree with trial kinds")
    roster = set(product(manifest["models"], manifest["seeds"], manifest["tasks"], manifest["conditions"]))
    extra = records.keys() - roster
    if extra:
        raise ValueError(f"trial outside the manifest: {min(extra)}")
    return manifest, records, roster


def paired(group, comparator, expected, numerator="gpp_fragment", include_raw=False):
    left = {key[:3]: t for key, t in group.items() if key[3] == numerator}
    right = {key[:3]: t for key, t in group.items() if key[3] == comparator}
    pairs = sorted(left.keys() & right.keys())
    tasks = defaultdict(list)
    for key in pairs:
        g, b = left[key], right[key]
        tasks[g.task].append((1, g.accepted, b.accepted, g.tokens, b.tokens, g.wall_ms, b.wall_ms))
    clusters = [tuple(map(sum, zip(*rows))) for rows in tasks.values()]
    assigned = expected if expected is not None else "?"
    columns = (0, 1, 2, 3) if include_raw else (0, 2, 3)
    if not clusters:
        return (comparator, f"0/{assigned}", 0, *("undefined" for _ in columns), "incomplete")
    point = metrics(clusters)  # acceptance difference, raw token ratio, token/accepted ratio, time/accepted ratio
    rng = random.Random(BOOTSTRAP_SEED)
    draws = ([metrics(rng.choices(clusters, k=len(clusters))) for _ in range(BOOTSTRAP_DRAWS)]
             if len(clusters) >= 2 else [])
    endpoints = {}
    cells = []
    for i in columns:
        if point[i] is None or not draws:
            cells.append(pretty(point[i], 4) + (" (interval unavailable)" if not draws else ""))
            continue
        finite = sorted(d[i] for d in draws if d[i] is not None)
        missing = len(draws) - len(finite)
        lo_idx = math.ceil(0.025 * len(draws)) - 1 - missing
        hi_idx = math.ceil(0.975 * len(draws)) - 1
        lo = finite[lo_idx] if lo_idx >= 0 else 0
        hi = finite[hi_idx] if hi_idx < len(finite) else math.inf
        endpoints[i] = (lo, hi)
        cells.append(f"{pretty(point[i], 4)} [{pretty(lo, 4)}, {pretty(hi, 4)}]" +
                     (f" ({missing} undefined draws)" if missing else ""))
    if len(pairs) != expected:
        assessment = "incomplete"
    elif not {0, 2} <= endpoints.keys():
        assessment = "unestimable"
    elif endpoints[0][0] >= -2 and endpoints[2][1] <= 0.80:
        assessment = "both bounds met"
    else:
        assessment = "bounds not both met"
    return (comparator, f"{len(pairs)}/{assigned}", len(clusters), *cells, assessment)


def detail(name, group, expected, conditions=CONDITIONS):
    print(f"\n## {safe(name)}")
    rows = []
    for cond in conditions:
        trials = [t for key, t in group.items() if key[3] == cond]
        count = sum(t.accepted for t in trials)
        tokens = sum(t.tokens for t in trials)
        elapsed = sum(t.wall_ms for t in trials) / 1000
        rows.append((cond, sum(len(t.outcomes) for t in trials),
                     rate(sum(t.first for t in trials), len(trials)), rate(count, len(trials)),
                     sum(t.inputs for t in trials), sum(t.outputs for t in trials), tokens,
                     pretty(tokens / count if count else None), pretty(elapsed / count if count else None),
                     pretty(sum(t.model_ms for t in trials) / 1000),
                     pretty(sum(t.tool_ms for t in trials) / 1000), pretty(elapsed)))
    table(["Condition", "Calls", "First accepted", "Final accepted", "Input tokens", "Output tokens",
           "All tokens", "Tokens/accepted", "Wall s/accepted", "Model s", "Tool s", "Wall s"], rows)
    headers = ["Comparator", "Matched/assigned", "Tasks", "Acceptance Δ (pp)"]
    tail = ["Tokens/accepted ratio", "Wall s/accepted ratio", "Acceptance and token bounds"]
    if conditions == REPLICATION:
        table(["Numerator", *headers, "All-token ratio", *tail],
              [(num, *paired(group, comp, expected, num, include_raw=True))
               for num in REPLICATION_NUMERATORS for comp in REPLICATION_COMPARATORS])
    else:
        table([*headers, *tail], [paired(group, comp, expected) for comp in CONDITIONS[1:]])


def report(manifest, records, roster):
    replication = "gpp_fim" in manifest["conditions"]
    conditions = REPLICATION if replication else CONDITIONS
    if replication:
        print("# Matched GPT++ authoring replication")
        print(f"\n{len(records)}/{len(roster)} assigned trials completed. The primary numerator is "
              "gpp_fim and the secondary numerator is gpp_projected. Both compare with python_fim, "
              "rust_fim and gpp_chat on the same task, model and seed. All attempts contribute usage.")
    else:
        print("# Fragment authoring pilot")
        print(f"\n{len(records)}/{len(roster)} assigned trials completed. Each comparison uses GPT++ "
              "fragment as its numerator and matches task, model and seed. All attempts contribute usage.")
    missing = sorted(roster - records.keys())
    if missing:
        table(["Missing model", "Seed", "Task", "Condition"], missing)
    print(f"\nBrackets are 95% percentile intervals from {BOOTSTRAP_DRAWS:,} deterministic task-cluster "
          f"resamples (seed {BOOTSTRAP_SEED}). Each task retains its model and seed runs. Draws with an "
          "undefined ratio may occupy either tail. The pilot screens for an acceptance lower bound of "
          "−2 pp or greater and a tokens/accepted upper ratio of 0.8000 or lower.")
    print("\nTokens are Ollama's reported input and generated token counts, including rendered "
          "context and all retries. The total weights input and output equally. Wall time includes "
          "model calls and public tool checks. The log records held-out scoring time separately. "
          "Adapters differ in validation, compilation and process startup. Financial savings "
          "require a declared cost model and independent qualification.")
    assigned = len(roster) // len(conditions)
    detail("All models", records, assigned, conditions)
    for model in manifest["models"]:
        detail(model, {k: v for k, v in records.items() if k[0] == model},
               assigned // len(manifest["models"]), conditions)
    if replication:
        kinds = manifest.get("task_kinds") or {t.task: t.kind for t in records.values()}
        known_kinds = len(kinds) == len(manifest["tasks"])
        if not known_kinds:
            print("\nSome assigned tasks have no records and no declared kind. "
                  "The kind-specific assignment counts remain unknown.")
        for kind in ("synthesis", "maintenance"):
            tasks = [task for task, task_kind in kinds.items() if task_kind == kind]
            expected = len(tasks) * len(manifest["models"]) * len(manifest["seeds"]) if known_kinds else None
            detail(kind.capitalize(), {k: t for k, t in records.items() if t.kind == kind}, expected, conditions)
    print("\n## Attempt outcomes")
    attempts, stops, failed = Counter(), Counter(), Counter()
    for (_, _, _, cond), trial in records.items():
        attempts.update((cond, outcome) for outcome in trial.outcomes)
        if not trial.accepted:
            failed[cond, trial.outcomes[-1] if trial.outcomes else "(no attempts)"] += 1
        stops.update((cond, reason or "unspecified") for reason in trial.stop_reasons)
    table(["Condition", "Outcome", "All attempts", "Terminal failures"],
          [(c, outcome, attempts[c, outcome], failed[c, outcome])
           for c, outcome in sorted(attempts.keys() | failed.keys())])
    table(["Condition", "Generation stop", "Calls"], [(c, reason, n) for (c, reason), n in sorted(stops.items())])


def repair_cost(log, conditions):
    # A first call that failed public examples already failed acceptance. For one
    # that passed, the runner recorded the held-out verdict before ending the trial.
    # This makes the no-retry result observable without generating counterfactual code.
    totals = {c: Counter() for c in conditions}
    with log.open() as stream:
        for line in stream:
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("type") == "metadata":
                continue
            acc = totals[r["condition"]]
            first, *later = r["attempts"]
            acc["tokens"] += first["input_tokens"] + first["output_tokens"]
            acc["first"] += r["first_accepted"]
            acc["repairs"] += len(later)
            acc["gained"] += r["accepted"] and not r["first_accepted"]
            acc["repair_tokens"] += sum(a["input_tokens"] + a["output_tokens"] for a in later)
    print("\n## Cost of the public-feedback repair")
    print("\nThe first-call columns count the observed initial calls and their acceptance. "
          "The repair columns count the additional calls, tokens and accepted trials.")
    table(["Condition", "First-call tokens", "First accepted", "First-call tokens/accepted",
           "Repair calls", "Additional tokens", "Additional accepted"],
          [(c, t["tokens"], t["first"], pretty(t["tokens"] / t["first"] if t["first"] else None),
            t["repairs"], t["repair_tokens"], t["gained"]) for c, t in totals.items()])


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("log", type=Path)
    try:
        log = cli.parse_args().log
        manifest, records, roster = load(log)
        report(manifest, records, roster)
        repair_cost(log, manifest["conditions"])
    except (ValueError, OSError) as err:
        cli.exit(1, f"{err}\n")
