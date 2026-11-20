"""Summarize localization, acceptance, and paired cost ratios from a complete archive."""

import argparse
from dataclasses import dataclass
from itertools import product
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "iterate"))
from report import paired, pretty, table


@dataclass
class Measurement:
    task: str
    accepted: bool
    tokens: int
    wall_ms: float


def report(path):
    with path.open() as stream:
        meta = json.loads(next(stream))
        rows = [json.loads(s) for s in stream]
    axes = (meta["models"], meta["tasks"], meta["conditions"])
    roster = set(product(*axes))
    if {(r["model"], r["task"], r["condition"]) for r in rows} != roster or len(rows) != len(roster):
        raise ValueError("Report requires the entire assigned matrix")
    print("# Expression-edit benchmark results")
    print(
        f"\n{len(meta['tasks'])} tasks, {len(rows)} assigned trials and "
        f"{sum(len(r['attempts']) for r in rows)} local model calls. "
        f"{meta['public_cases']} public and {meta['hidden_cases']} withheld examples. "
        f"{meta['reference_cases_checked']} cross-language reference observations. "
        "Given-site trials receive the expression location. Separate and combined selection pay for the model to find it."
    )
    for model in meta["models"]:
        current = [r for r in rows if r["model"] == model]
        print("\n## " + model)
        table_rows, samples = [], {}
        for arm in meta["conditions"]:
            group = [r for r in current if r["condition"] == arm]
            loc_calls = [a for r in group for a in r["attempts"] if a["stage"] == "location"]
            selections = [a for r in group for a in r["attempts"] if a["stage"] in ("location", "change")]

            def count_tokens(calls):
                return sum(a["input_tokens"] + a["output_tokens"] for a in calls)

            initial = 0
            total = 0
            for r in group:
                usage = count_tokens([a for a in r["attempts"] if a["stage"] != "retry"])
                initial += usage
                total += count_tokens(r["attempts"])
                samples[(model, 42, r["task"], arm)] = Measurement(r["task"], r["first_accepted"], usage, 0)
            first, final = sum(r["first_accepted"] for r in group), sum(r["accepted"] for r in group)
            table_rows.append(
                [
                    arm,
                    f"{sum(a.get('located') or a['outcome'] == 'located' for a in selections)}/{len(selections)}"
                    if selections
                    else "—",
                    count_tokens(loc_calls),
                    f"{first}/{len(group)}",
                    initial,
                    pretty(initial / first if first else None),
                    sum(a["stage"] == "retry" for r in group for a in r["attempts"]),
                    f"{final}/{len(group)}",
                    total,
                    pretty(total / final if final else None),
                    pretty(sum(a["model_ms"] for r in group for a in r["attempts"]) / 1000),
                    pretty(
                        sum(r["wall_ms"] - sum(a["model_ms"] for a in r["attempts"]) for r in group) / 1000
                    ),
                ]
            )
        table(
            [
                "Arm",
                "Valid locations",
                "Separate location tokens",
                "First accepts",
                "First total tokens",
                "First tokens/accept",
                "Retries",
                "Final accepts",
                "Final total tokens",
                "Final tokens/accept",
                "Model s",
                "Local checks and overhead s",
            ],
            table_rows,
        )
        print(
            "\nOne-edit-attempt comparisons count location calls. A ratio of 0.80 represents 20% fewer tokens per accepted change. "
            "The gate also requires the paired 95% upper ratio bound to reach 0.80 and the lower acceptance difference to reach −2 percentage points."
        )
        pairs = [
            ("gpp_locate", arm)
            for arm in ("python_locate", "rust_locate", "python_full", "rust_full", "gpp_full")
        ]
        pairs += [("gpp_given", arm) for arm in ("python_given", "rust_given", "gpp_full")]
        pairs += [
            ("gpp_combined", arm) for arm in ("python_combined", "rust_combined", "gpp_locate", "gpp_full")
        ]
        pair_rows = []
        for numerator, baseline in pairs:
            _, _, _, accept_delta, _, cost, _, gate = paired(
                samples, baseline, len(meta["tasks"]), numerator, True
            )
            pair_rows.append([numerator, baseline, accept_delta, cost, gate])
        table(
            [
                "GPT++ arm",
                "Comparator",
                "Acceptance difference, pp [95% interval]",
                "Tokens/accept ratio [95% interval]",
                "Gate",
            ],
            pair_rows,
        )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("archive", type=Path)
    report(cli.parse_args().archive)
