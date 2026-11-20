"""Summarize the paired marginal language comparison without treating repeated models as new families."""

import argparse
from pathlib import Path
import json


def paired(records):
    trials = [row for row in records if row.get("kind") == "trial"]
    calls = [row for row in records if row.get("kind") == "call"]
    by = {(r["model"], r["task"], r["language"]): r for r in trials}
    assignments = {(r["model"], r["task"]) for r in trials}
    if len(assignments) != 8 or len(by) != 24 or len(trials) != len(by):
        raise ValueError("Expected eight complete matched triples")
    total = {}
    for language in ("gpp", "rust", "python"):
        group = [r for r in trials if r["language"] == language]
        complete = sum(r["accepted"] for r in group)
        used = sum(
            r["reply"]["prompt_eval_count"] + r["reply"]["eval_count"]
            for r in calls
            if r["language"] == language
        )
        total[language] = (complete, used, used / complete if complete else None)
    print("# Comparing the language under a shared edit interface\n")
    print(
        "Each paired assignment is one model working on the same change in both languages. "
        "There are four task families and two models. A win means GPT++ alone passed the visible "
        "contracts and withheld sequence tests. A loss means the comparator alone passed. A tie "
        "includes both passing and both failing.\n"
    )
    print("| Comparator | GPT++ wins | GPT++ losses | Both pass | Both fail |")
    print("|---|---:|---:|---:|---:|")
    for language in ("rust", "python"):
        pairs = [(by[m, t, "gpp"]["accepted"], by[m, t, language]["accepted"]) for m, t in assignments]
        print(
            f"| {language} | {pairs.count((True, False))} | {pairs.count((False, True))} | "
            f"{pairs.count((True, True))} | {pairs.count((False, False))} |"
        )
    print("\n| Language | Accepted | Total model tokens | Tokens per accepted change |")
    print("|---|---:|---:|---:|")
    for language, (count, tokens, cost) in total.items():
        per = f"{cost:,.1f}" if cost is not None else "undefined"
        print(f"| {language} | {count}/8 | {tokens:,} | {per} |")
    print(
        "\nToken totals pool the two pinned model configurations and charge failed trials and retries. "
        "The per-model results report each tokenizer separately. All programs used the same typed "
        "expression slot and behavior checks. Differences in syntax, model familiarity, compiler "
        "interfaces and validation time are still combined within each native arm. The comparison "
        "does not establish a language-wide advantage."
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("archive", type=Path)
    args = cli.parse_args()
    paired([json.loads(line) for line in args.archive.read_text().splitlines()])
