"""Write a paired scalar-authoring pilot report to stdout from a JSONL run log."""

import argparse
import json
import math
import random
from statistics import median
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import product
from pathlib import Path

LANGUAGES = ("gpp", "rust", "python")
BOOTSTRAP_DRAWS = 10000
BOOTSTRAP_SEED = 20261119


def field(row, key, allowed):
    value = row[key]
    if type(value) not in allowed:
        raise ValueError(f"invalid type for {key}")
    if type(value) is str and not value.strip():
        raise ValueError(f"empty {key}")
    return value


def amount(row, key, allowed):
    value = field(row, key, allowed)
    if value < 0 or not math.isfinite(value):
        raise ValueError(f"{key} must be finite and nonnegative")
    return value


@dataclass(frozen=True)
class Trial:
    model: str
    task: str
    kind: str
    language: str
    seed: int
    accepted: bool
    first: bool
    outcomes: tuple
    stop_reasons: tuple
    inputs: int
    outputs: int
    model_ms: float
    tool_ms: float
    wall_ms: float

    @property
    def tokens(self):
        return self.inputs + self.outputs

    @classmethod
    def parse(cls, row):
        language = field(row, "language", {str})
        kind = field(row, "kind", {str})
        if language not in LANGUAGES or kind not in ("maintenance", "synthesis"):
            raise ValueError(f"unsupported language or task kind ({language}, {kind})")
        attempts = field(row, "attempts", {list})
        first, accepted = (field(row, key, {bool}) for key in ("first_accepted", "accepted"))
        if first and not accepted or accepted and not attempts:
            raise ValueError("inconsistent acceptance fields")
        return cls(field(row, "model", {str}), field(row, "task", {str}), kind, language,
                   field(row, "seed", {int}), accepted, first,
                   tuple(field(a, "outcome", {str}) for a in attempts),
                   tuple(a.get("done_reason") for a in attempts),
                   sum(amount(a, "input_tokens", {int}) for a in attempts),
                   sum(amount(a, "output_tokens", {int}) for a in attempts),
                   sum(amount(a, "model_ms", {int, float}) for a in attempts),
                   sum(amount(a, "tool_ms", {int, float}) for a in attempts),
                   amount(row, "wall_ms", {int, float}))


def load(path):
    trials, metadata, kinds = {}, None, {}
    with path.open(encoding="utf-8") as data:
        for line_no, line in enumerate(data, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("expected a JSON object")
                if row.get("type") == "metadata":
                    if metadata is not None or trials:
                        raise ValueError("expected a single leading metadata record")
                    metadata = row
                    continue
                t = Trial.parse(row)
                key = (t.model, t.seed, t.task, t.language)
                if key in trials:
                    raise ValueError(f"duplicate trial {key}")
                if kinds.setdefault(t.task, t.kind) != t.kind:
                    raise ValueError(f"conflicting task kinds for {t.task}")
                trials[key] = t
            except (KeyError, ValueError, TypeError, OverflowError) as err:
                raise ValueError(f"{path}:{line_no}: {err}") from err
    return metadata, trials


def safe(value):
    return " ".join(str(value).splitlines()).replace("|", "\\|")


def table(headers, rows):
    print()
    print("| " + " | ".join(headers) + " |")
    print("|" + "|".join("---" for _ in headers) + "|")
    for row in rows:
        print("| " + " | ".join(map(safe, row)) + " |")


def coverage(metadata, trials):
    meta = metadata or {}
    observed = list(zip(*trials)) if trials else [(), (), (), ()]
    axes = []
    for key, seen, ty in zip(("models", "seeds", "tasks"), observed, (str, int, str)):
        planned = meta.get(key)
        declared = isinstance(planned, list) and all(type(x) is ty for x in planned)
        if declared and set(seen) - set(planned):
            print(f"\nObserved {key} outside the declared roster: "
                  + ", ".join(safe(x) for x in sorted(set(seen) - set(planned))) + ".")
        axes.append(sorted(set(seen) | (set(planned) if declared else set())))
    models, seeds, tasks = axes
    roster = set(product(models, seeds, tasks, LANGUAGES))
    missing = sorted(roster - trials.keys())
    print(f"\nThe planned pilot has 72 trials (12 tasks × 2 models × 1 seed × 3 languages). "
          f"The log contains {len(trials)} completed trials. The observed or declared roster "
          f"has {len(tasks)} tasks, {len(models)} models and {len(seeds)} seed values.")
    if metadata is not None:
        print("\nCoverage uses the identities declared in the run manifest.")
    else:
        print("\nCoverage uses the observed identities. A complete roster requires a manifest.")
    if missing:
        rows = defaultdict(list)
        for model, seed, task, language in missing:
            rows[model, seed, language].append(task)
        print(f"\nMissing {len(missing)} of {len(roster)} cells on this roster.")
        table(["Model", "Seed", "Language", "Missing task IDs"],
              [(m, s, lang, ", ".join(ids)) for (m, s, lang), ids in rows.items()])
    elif roster:
        print(f"\nAll {len(roster)} cells on this roster are present.")
    return models


def pretty(number, digits=2):
    if number is None:
        return "undefined"
    if math.isinf(number):
        return "∞"
    return f"{number:,.{digits}f}"


def rate(count, n):
    return f"{count}/{n} ({100 * count / n:.1f}%)" if n else "0/0 (undefined)"


def totals(trials):
    rows = []
    for lang in LANGUAGES:
        group = [t for t in trials if t.language == lang]
        accepted = sum(t.accepted for t in group)
        inputs, outputs = (sum(getattr(t, key) for t in group) for key in ("inputs", "outputs"))
        elapsed = sum(t.wall_ms for t in group) / 1000
        durations = sorted(t.wall_ms / 1000 for t in group)
        rows.append((lang, len(group), sum(len(t.outcomes) for t in group),
                     rate(sum(t.first for t in group), len(group)), rate(accepted, len(group)),
                     inputs, outputs, inputs + outputs,
                     pretty(sum(t.model_ms for t in group) / 1000),
                     pretty(sum(t.tool_ms for t in group) / 1000), pretty(elapsed),
                     pretty((inputs + outputs) / accepted if accepted else None),
                     pretty(elapsed / accepted if accepted else None),
                     pretty(median(durations) if durations else None),
                     pretty(durations[math.ceil(0.95 * len(durations)) - 1] if durations else None)))
    table(["Language", "Trials", "Calls", "First accepted", "Final accepted", "Input tokens",
           "Output tokens", "All tokens", "Model s", "Tool s", "Wall s", "Tokens/accepted", "Wall s/accepted",
           "Median trial s", "P95 trial s"], rows)


def metrics(cluster_totals):
    n, success_g, success_b, tokens_g, tokens_b, wall_g, wall_b = map(sum, zip(*cluster_totals))

    def per_accepted_ratio(g, b):
        return (g * success_b) / (b * success_g) if success_g and success_b and b else None

    return (100 * (success_g - success_b) / n,
            tokens_g / tokens_b if tokens_b else None,
            per_accepted_ratio(tokens_g, tokens_b), per_accepted_ratio(wall_g, wall_b))


def paired(gpp, baseline):
    keys = sorted(gpp.keys() & baseline.keys())
    by_task = defaultdict(list)
    for key in keys:
        g, b = gpp[key], baseline[key]
        by_task[g.task].append((1, g.accepted, b.accepted, g.tokens, b.tokens, g.wall_ms, b.wall_ms))
    clusters = [tuple(map(sum, zip(*pairs))) for pairs in by_task.values()]
    if not clusters:
        return (0, 0, *(["undefined"] * 4))
    point = metrics(clusters)
    if len(clusters) == 1:
        return (len(keys), 1, *(f"{pretty(x, 3)} [interval unavailable]" for x in point))

    rng = random.Random(BOOTSTRAP_SEED)
    draws = [metrics(rng.choices(clusters, k=len(clusters))) for _ in range(BOOTSTRAP_DRAWS)]
    estimates = []
    for i, estimate in enumerate(point):
        if estimate is None:
            estimates.append("undefined")
            continue
        finite = sorted(draw[i] for draw in draws if draw[i] is not None)
        missing = len(draws) - len(finite)
        # Keep undefined draws in the distribution. They can occupy either tail
        # of a nonnegative ratio, so the bounds widen instead of conditioning on success.
        lower_index = math.ceil(0.025 * len(draws)) - 1 - missing
        upper_index = math.ceil(0.975 * len(draws)) - 1
        lower = finite[lower_index] if lower_index >= 0 else 0.0
        upper = finite[upper_index] if upper_index < len(finite) else math.inf
        value = f"{pretty(estimate, 3)} [{pretty(lower, 3)}, {pretty(upper, 3)}]"
        estimates.append(value + (f" ({missing} undefined draws)" if missing else ""))
    return (len(keys), len(clusters), *estimates)


def slice_report(name, group):
    print(f"\n## {safe(name)}")
    totals(group)
    by_language = {lang: {(t.model, t.seed, t.task): t for t in group if t.language == lang}
                   for lang in LANGUAGES}
    rows = [(f"GPT++ / {base}", *paired(by_language["gpp"], by_language[base]))
            for base in ("rust", "python")]
    table(["Pair", "Matched trials", "Tasks", "Final acceptance Δ (pp)", "All-token ratio",
           "Tokens/accepted ratio", "Wall s/accepted ratio"], rows)


def report(metadata, trials):
    print("# Scalar authoring pilot")
    models = coverage(metadata, trials)
    group = list(trials.values())
    kinds = Counter(t.kind for t in group)
    print(f"\nCompleted trials include {kinds['synthesis']} synthesis and {kinds['maintenance']} maintenance assignments. "
          "Totals include failed calls and repairs. Model, tool and trial wall times are reported separately.")
    print(f"\nComparisons pair the same model, seed and task. Each estimate uses its available pairs. "
          f"Brackets give 95% percentile intervals from {BOOTSTRAP_DRAWS:,} task-cluster resamples "
          f"with seed {BOOTSTRAP_SEED}. Each sampled task retains all its matched model and seed runs. "
          "Undefined ratio draws may occupy either tail. One task cannot estimate sampling uncertainty.")
    print("\nThe design's 20% target requires a cost-ratio upper endpoint of 0.800 or lower. "
          "Its acceptance margin requires a lower endpoint of at least −2 percentage points. "
          "Tokens and elapsed time measure different aspects of computational effort. "
          "Qualification requires a separate study and a defined cost model.")
    slice_report("All models", group)
    for model in models:
        slice_report(model, [t for t in group if t.model == model])
    for kind in ("synthesis", "maintenance"):
        slice_report(kind.capitalize(), [t for t in group if t.kind == kind])
    print("\n## Generation limits")
    stop_reasons = defaultdict(list)
    for trial in group:
        stop_reasons[trial.model, trial.language].extend(trial.stop_reasons)
    table(["Model", "Language", "Calls", "Output limit reached"],
          [(model, lang, len(reasons), reasons.count("length"))
           for (model, lang), reasons in sorted(stop_reasons.items())])
    print("\n## Attempt outcomes and terminal failures")
    attempts, failures = Counter(), Counter()
    for t in group:
        attempts.update((t.language, result) for result in t.outcomes)
        if not t.accepted:
            failures[t.language, t.outcomes[-1] if t.outcomes else "(no attempt)"] += 1
    table(["Language", "Outcome", "Attempts", "Final unaccepted trials"],
          [(lang, result, attempts[lang, result], failures[lang, result])
           for lang, result in sorted(attempts.keys() | failures.keys())])


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("run_log", type=Path, help="JSONL file containing completed assigned trials")
    args = cli.parse_args()
    try:
        report(*load(args.run_log))
    except (OSError, ValueError) as error:
        cli.exit(1, f"{error}\n")
