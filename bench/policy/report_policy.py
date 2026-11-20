"""Print a paired, task-clustered report from a completed policy-maintenance run."""

import argparse
from collections import Counter
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "iterate"))
from report import Trial, paired, pretty, table


def render(path):
    with path.open() as stream:
        meta = json.loads(next(stream))
        rows = [json.loads(s) for s in stream]
    arms, models, tasks = [meta[k] for k in ("conditions", "models", "tasks")]
    assigned = {(m, t, a) for m in models for t in tasks for a in arms}
    if len(rows) != len(assigned) or {(r["model"], r["task"], r["condition"]) for r in rows} != assigned:
        raise ValueError("Report requires exactly one trial per assigned cell")
    print("# " + meta["study"])
    print(
        f"\n{len(tasks)} paired task families per model. {meta['public_cases']} public and "
        f"{meta['hidden_cases']} withheld examples. {meta['reference_cases_checked']} cross-language reference "
        f"checks. {len(rows)} trials and {sum(len(r['attempts']) for r in rows)} measured model calls."
    )
    for model in models:
        print("\n## " + model)
        selected = meta.get("selected", {}).get(model)
        primary = selected["gpp"] if selected else meta["primary"]
        if selected:
            print(
                f"\nWorkflows selected on development data were {primary}, {selected['python']} and {selected['rust']}."
            )
        group = {}
        counts = []
        for arm in arms:
            entries = [r for r in rows if r["model"] == model and r["condition"] == arm]
            trials = [Trial.parse(r) for r in entries]
            group.update({(t.model, t.seed, t.task, arm): t for t in trials})
            accepted = sum(t.accepted for t in trials)
            first = sum(t.first for t in trials)
            initial_tokens = sum(
                r["attempts"][0]["input_tokens"] + r["attempts"][0]["output_tokens"] for r in entries
            )
            inp, out = sum(t.inputs for t in trials), sum(t.outputs for t in trials)
            counts.append(
                (
                    arm,
                    first,
                    pretty(initial_tokens / first if first else None),
                    sum(len(t.outcomes) - 1 for t in trials),
                    accepted - first,
                    inp + out - initial_tokens,
                    f"{accepted}/{len(trials)}",
                    inp,
                    out,
                    pretty((inp + out) / accepted if accepted else None),
                    pretty(sum(t.wall_ms for t in trials) / 1000 / accepted if accepted else None),
                )
            )
        table(
            [
                "Condition",
                "First accepts",
                "First-call tokens/accept",
                "Retries",
                "Added accepts",
                "Retry tokens",
                "Final accepts",
                "Input tokens",
                "Output tokens",
                "All tokens/accept",
                "Wall s/accept",
            ],
            counts,
        )
        comparisons = [a for a in arms if a != primary]
        head = [
            "Comparator",
            "Matched",
            "Families",
            "Acceptance Δ (pp)",
            "Total token ratio",
            "Tokens/accepted ratio (95% interval)",
            "Time/accepted ratio",
            "Gate",
        ]
        table(head, [paired(group, comp, len(tasks), primary, True) for comp in comparisons])

        def cost(arm):
            c = [t for k, t in group.items() if k[3] == arm]
            n = sum(t.accepted for t in c)
            return sum(t.tokens for t in c) / n if n else None

        main = cost(primary)
        distance = []
        for comp in comparisons:
            base = cost(comp)
            threshold = 0.8 * base if base is not None else None
            ratio = main / base if main is not None and base else None
            distance.append(
                (
                    comp,
                    pretty(threshold),
                    pretty(100 * (1 - ratio) if ratio is not None else None),
                    pretty(100 * (ratio - 0.8) if ratio is not None else None),
                    pretty(main - threshold if main is not None and threshold is not None else None),
                )
            )
        print("\nA positive shortfall is the additional improvement required to reach 20% savings.")
        table(
            [
                "Comparator",
                "20% target in tokens/accept",
                "Observed saving (%)",
                "Shortfall (pp)",
                "Shortfall (tokens/accept)",
            ],
            distance,
        )
        if selected:
            attempts = [a for r in rows if r["model"] == model for a in r["attempts"][1:]]
            print(
                f"\n{sum(a.get('obligation') is not None for a in attempts)} of {len(attempts)} caller retries "
                "received an exact derived target result. Other retries received the original excerpts."
            )
        verdicts = {a: Counter(t.outcomes[-1] for k, t in group.items() if k[3] == a) for a in arms}
        labels = sorted(set().union(*(v.keys() for v in verdicts.values())))
        table(["Terminal outcome", *arms], [(k, *[verdicts[a][k] for a in arms]) for k in labels])
    print(
        "\nWall time covers inference and public validation. Withheld evaluation is recorded separately. "
        "The intervals resample whole tasks. An undefined estimate means the run produced too few accepted edits "
        "to price a success. Costs use each model's own tokenizer."
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("log", type=Path)
    render(cli.parse_args().log)
