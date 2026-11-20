"""Summarize the paired, seven-condition completion-boundary pilot from its JSONL log."""

import argparse
from collections import Counter
from itertools import product
import json
from pathlib import Path

from report import BOOTSTRAP_DRAWS, BOOTSTRAP_SEED, Trial, paired, pretty, rate, repair_cost, safe, table
from summarize import amount


CONDITIONS = ("gpp_open", "gpp_stop", "rust_open", "rust_stop",
              "python_open", "python_stop", "gpp_projected_stop")
COMPARISONS = (
    ("gpp_stop", "gpp_open"), ("rust_stop", "rust_open"), ("python_stop", "python_open"),
    ("gpp_stop", "python_stop"), ("gpp_stop", "rust_stop"), ("gpp_projected_stop", "python_stop"),
)


def roster(manifest):
    axes = {}
    for name, count, ty in (("models", 1, str), ("seeds", 1, int),
                            ("tasks", 8, str), ("conditions", 7, str)):
        values = manifest.get(name)
        if (type(values) is not list or len(values) != count
                or any(type(v) is not ty or (ty is str and not v.strip()) for v in values)
                or len(set(values)) != count):
            raise ValueError(f"invalid manifest {name}: expected {count} distinct {ty.__name__} values")
        axes[name] = values
    if set(axes["conditions"]) != set(CONDITIONS):
        raise ValueError("manifest must declare the seven v4 conditions")
    return set(product(axes["models"], axes["seeds"], axes["tasks"], CONDITIONS))


def load(log):
    manifest, assigned, trials, heldout, kinds = None, set(), {}, {}, {}
    with log.open(encoding="utf-8") as stream:
        for lineno, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("expected a JSON object")
                if row.get("type") == "metadata":
                    if manifest is not None or trials:
                        raise ValueError("expected one leading manifest")
                    manifest, assigned = row, roster(row)
                    continue
                if manifest is None:
                    raise ValueError("missing leading manifest")
                trial = Trial.parse(row)
                cond = row["condition"]
                key = (trial.model, trial.seed, trial.task, cond)
                if key not in assigned or key in trials:
                    raise ValueError(f"unexpected or duplicate assigned trial {key}")
                if cond.split("_")[0] != trial.language:
                    raise ValueError(f"target language {trial.language} disagrees with {cond}")
                if kinds.setdefault(trial.task, trial.kind) != trial.kind:
                    raise ValueError(f"conflicting kinds for task {trial.task}")
                if (not 1 <= len(trial.outcomes) <= 2 or trial.accepted != (trial.outcomes[-1] == "accepted")
                        or trial.first != (trial.accepted and len(trial.outcomes) == 1)):
                    raise ValueError("inconsistent number of attempts or acceptance verdicts")
                heldout[key] = amount(row, "heldout_ms", {int, float})
                trials[key] = trial
            except (KeyError, ValueError, TypeError, OverflowError) as err:
                raise ValueError(f"{log}:{lineno}: {err}") from err
    if manifest is None:
        raise ValueError("expected an eight-task boundary study manifest")
    if "task_kinds" in manifest:
        declared = manifest["task_kinds"]
        if (not isinstance(declared, dict) or set(declared) != set(manifest["tasks"])
                or any(k not in ("synthesis", "maintenance") for k in declared.values())
                or any(declared[k] != v for k, v in kinds.items())):
            raise ValueError("task kinds must match manifest and trial records")
    return manifest, assigned, trials, heldout


def report(manifest, assigned, records, heldout):
    model = safe(manifest["models"][0])
    print("# Completion-boundary pilot")
    print(f"\n{len(records)}/{len(assigned)} assigned trials completed for {model}, "
          f"seed {manifest['seeds'][0]}, across eight tasks and seven conditions.")
    missing = sorted(assigned - records.keys())
    if missing:
        print("\nCounts and costs below are provisional. The two acceptance columns count observed "
              "successes against all assigned trials. Unobserved trials have unknown outcomes and costs.")
        table(["Missing model", "Seed", "Task", "Condition"], missing)
    print("\n## Assigned trials and observed costs")
    rows = []
    for cond in CONDITIONS:
        group = [t for key, t in records.items() if key[3] == cond]
        n = sum(key[3] == cond for key in assigned)
        count = sum(t.accepted for t in group)
        first = sum(t.first for t in group)
        tokens = sum(t.tokens for t in group)
        wall = sum(t.wall_ms for t in group) / 1000
        oracle = sum(ms for key, ms in heldout.items() if key[3] == cond) / 1000
        rows.append((cond, f"{len(group)}/{n}", sum(len(t.outcomes) for t in group),
                     rate(first, n), rate(count, n), sum(t.inputs for t in group),
                     sum(t.outputs for t in group), tokens, pretty(tokens / count if count else None),
                     pretty(sum(t.model_ms for t in group) / 1000), pretty(sum(t.tool_ms for t in group) / 1000),
                     pretty(wall), pretty(oracle), pretty(wall / count if count else None),
                     pretty((wall + oracle) / count if count else None)))
    table(["Condition", "Completed", "Calls", "First accepted / assigned", "Final accepted / assigned",
           "Input tokens", "Output tokens", "All tokens", "Tokens/accepted", "Model s", "Public tool s",
           "Workflow s", "Held-out s", "Workflow s/accepted", "Workflow + held-out s/accepted"], rows)
    print("\nAll calls and repairs contribute to totals. Model time and public tool time are included "
          "in workflow time. The final column also includes held-out checking. Input and output tokens "
          "have equal weight here. Financial cost would require a pricing model.")

    print("\n## Paired comparisons")
    print(f"\nRatios use the first condition as numerator. Acceptance differences are percentage points. "
          f"Brackets are 95% percentile intervals using {BOOTSTRAP_DRAWS:,} task-cluster draws "
          f"(seed {BOOTSTRAP_SEED}). Each draw keeps all matched observations of a task together. "
          "Undefined draws may occupy either tail. The screen requires an acceptance lower bound "
          "of at least −2 pp and a tokens/accepted upper bound of at most 0.8000.")
    table(["Numerator", "Comparator", "Matched/assigned", "Tasks", "Final acceptance Δ (pp)",
           "All-token ratio", "Tokens/accepted ratio", "Workflow s/accepted ratio", "Pilot screen"],
          [(left, *paired(records, right, len(manifest["tasks"]), numerator=left, include_raw=True))
           for left, right in COMPARISONS])

    print("\n## Attempt and stop outcomes")
    attempts, failures, reasons = Counter(), Counter(), Counter()
    for key, trial in records.items():
        cond = key[3]
        attempts.update((cond, outcome) for outcome in trial.outcomes)
        reasons.update((cond, reason or "unspecified") for reason in trial.stop_reasons)
        if not trial.accepted:
            failures[cond, trial.outcomes[-1]] += 1
    table(["Condition", "Attempt outcome", "Calls", "Terminal failures"],
          [(c, result, n, failures[c, result]) for (c, result), n in sorted(attempts.items())])
    table(["Condition", "Generation stop reason", "Calls"],
          [(c, reason, n) for (c, reason), n in sorted(reasons.items())])


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("log", type=Path)
    try:
        log = cli.parse_args().log
        report(*load(log))
        repair_cost(log, CONDITIONS)
    except (ValueError, OSError) as err:
        cli.exit(1, f"{err}\n")
