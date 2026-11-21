"""Summarize a closed, independently scored five-arm comparison."""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
from itertools import product
import json
from math import ceil, comb, inf
from pathlib import Path

ARMS = ("direct", "direct_retry", "direct_witness", "search", "workflow")
LANGUAGES = ("gpp", "python", "rust")
NAMES = {"gpp": "GPT++", "python": "Typed Python", "rust": "Rust", "direct": "Direct",
         "direct_retry": "Direct + blind retry", "direct_witness": "Direct + witness",
         "search": "Compiler only", "workflow": "Workflow"}


def load(output):
    ledger = (output / "decisions.jsonl").read_bytes()
    rows = [json.loads(line) for line in ledger.splitlines()]
    scored = json.loads((output / "scores.json").read_text())
    if scored["decisions_sha256"] != sha256(ledger).hexdigest() or rows[-1]["kind"] != "closed":
        raise ValueError("A closed ledger and scores for that exact ledger are required")
    manifest, = [r for r in rows if r["kind"] == "manifest"]
    preflight, = [r for r in rows if r["kind"] == "preflight"]
    audit = {r["task"]: r for r in preflight["mutation_audit"]}
    if len(preflight["mutation_audit"]) != len(audit) or len(audit) != 6:
        raise ValueError("Expected exactly one metered preparation audit per family")
    groups = defaultdict(dict)
    calls = defaultdict(list)
    for r in rows:
        if r["kind"] == "call":
            calls[r["trial"]].append(r)
    for r in rows:
        if r["kind"] != "trial":
            continue
        score = scored["trials"][r["trial"]]
        published = r["decision"] == "accept"
        if published != (score["score"] is not None):
            raise ValueError(f"Publication/score mismatch for {r['trial']}")
        receipts = calls.pop(r["trial"], [])
        if len(receipts) != r["model_calls"] or any(sum(c[k] for c in receipts) != r[k]
                                                    for k in ("input_tokens", "output_tokens")):
            raise ValueError(f"Model receipt mismatch for {r['trial']}")
        correct = published and score["score"]["wrong"] == 0
        question = r.get("question") or {}
        group = groups[r["language"], r["arm"]]
        if r["task"] in group:
            raise ValueError(f"Duplicate assignment {r['trial']}")
        group[r["task"]] = dict(
            correct=correct, wrong=published and not correct, abstained=not published,
            first_correct=correct and r["first_pass"], first_published=r["first_pass"], published=published,
            calls=r["model_calls"], rejected=sum(c["decision"] != "accept" for c in r["candidates"]),
            retries=sum(c["source"] == "model:repair" for c in r["candidates"]),
            questions=int(bool(question)), labels=question.get("labels", 0), authority_calls=question.get("calls", 0),
            input=r["input_tokens"] + question.get("input_tokens", 0),
            output=r["output_tokens"] + question.get("output_tokens", 0),
            audit_input=audit[r["task"]]["input_tokens"], audit_output=audit[r["task"]]["output_tokens"],
            audit_model=audit[r["task"]]["model_seconds"],
            model=r["model_seconds"], tool=r["tool_seconds"], wall=r["wall_seconds"], scoring=score["seconds"],
        )
    tasks = sorted(r["task"] for r in preflight["results"])
    if (len(tasks) != 6 or len(set(tasks)) != 6 or calls or len(groups) != 15
            or any(set(groups[k]) != set(tasks) for k in product(LANGUAGES, ARMS))):
        raise ValueError("The complete six-family, three-language, five-arm roster is required")
    return (manifest, tasks, groups, sum(r["seconds"] for r in preflight["results"]),
            preflight["audit_wall_seconds"], scored["calibration_seconds"])


def totals(rows):
    return Counter({key: sum(row[key] for row in rows.values()) for key in next(iter(rows.values()))})


def tokens(row):
    return row["input"] + row["output"] + row["audit_input"] + row["audit_output"]


def exact_binomial(k, n):
    # Two 97.5% Clopper-Pearson marginal intervals yield joint coverage >=95%.
    # Bisection inverts the exact binomial tail, monotone in p.
    def upper_tail(j, p):
        return sum(comb(n, i) * p**i * (1 - p)**(n - i) for i in range(j, n + 1))

    def inverse(j, probability):
        lo, hi = 0., 1.
        for _ in range(60):
            mid = (lo + hi) / 2
            if upper_tail(j, mid) < probability:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    return (inverse(k, .0125) if k else 0., inverse(k + 1, .9875) if k < n else 1.)


def compare(left, right, tasks):
    wins = [t for t in tasks if left[t]["correct"] and not right[t]["correct"]]
    losses = [t for t in tasks if right[t]["correct"] and not left[t]["correct"]]
    both = sum(left[t]["correct"] and right[t]["correct"] for t in tasks)
    n = len(tasks)
    win_ci, loss_ci = exact_binomial(len(wins), n), exact_binomial(len(losses), n)
    return wins, losses, both, n - len(wins) - len(losses) - both, (win_ci[0] - loss_ci[1], win_ci[1] - loss_ci[0])


def ratio(a_tokens, a_correct, b_tokens, b_correct):
    if not a_correct or not b_correct or not b_tokens:
        return None
    return a_tokens * b_correct / (b_tokens * a_correct)


def bootstrap(left, right, tasks):
    # Enumerate all equally likely ordered n-out-of-n paired family resamples.
    # Unknown ratios contribute their full [0, +infinity] envelope to quantiles.
    cells = [(tokens(left[t]), int(left[t]["correct"]), tokens(right[t]), int(right[t]["correct"])) for t in tasks]
    values = []
    missing = 0
    for sample in product(cells, repeat=len(tasks)):
        value = ratio(*map(sum, zip(*sample)))
        if value is None:
            missing += 1
        else:
            values.append(value)
    if not values:
        return None, missing / (len(tasks)**len(tasks))
    values.sort()
    n = len(values) + missing
    lo, hi = ceil(.025 * n) - 1, ceil(.975 * n) - 1
    return (0 if lo < missing else values[lo - missing], values[hi] if hi < len(values) else inf), missing / n


def num(value):
    return "undefined" if value is None else "∞" if value == inf else f"{value:.2f}"


def ci_text(ci):
    return f"[{100*ci[0]:.1f}, {100*ci[1]:.1f}]"


def sensitivity(workflow, direct):
    wc, dc = workflow["correct"], direct["correct"]
    if not wc or not dc or not tokens(direct):
        return "The primary cost ratio and its preparation-token threshold are undefined."
    # After charging the same unmetered preparation P to each method, the cost
    # target is equivalent to coefficient * P <= allowance.
    coefficient = dc - .8 * wc
    allowance = .8 * wc * tokens(direct) - dc * tokens(workflow)
    if coefficient > 0 and allowance >= 0:
        return f"Charging each arm more than {allowance / coefficient:,.0f} additional shared preparation tokens would erase the observed 20% cost saving."
    if coefficient < 0 and allowance < 0:
        return f"The cost point estimate would first meet the target at {allowance / coefficient:,.0f} additional shared preparation tokens per arm, due to the different success counts."
    if allowance < 0:
        return "Charging both arms the same nonnegative preparation-token total cannot bring the observed cost ratio within target."
    return "The observed cost ratio remains within target for every equal, nonnegative preparation-token charge."


def report(output):
    manifest, tasks, groups, public_cal, audit_wall, sealed_cal = load(output)
    prep = manifest["prep"]
    setup = prep["wall_seconds"] + public_cal + sealed_cal + audit_wall
    summary = {k: totals(rows) for k, rows in groups.items()}
    direct, workflow = (summary["gpp", arm] for arm in ("direct", "workflow"))
    primary = ratio(tokens(workflow), workflow["correct"], tokens(direct), direct["correct"])
    lines = ["# Fresh paired comparison", "",
             f"GPT++’s workflow produced {workflow['correct']}/6 independently correct edits in {workflow['calls']} model calls. One-call direct Qwen produced {direct['correct']}/6 in {direct['calls']} calls. Including the shared contract audit, tokens per correct edit had a workflow/direct ratio of {num(primary)}.", "",
             "## Acceptance and cost", "",
             "Each row covers six newly executed assignments. First C/P counts independently correct edits and publications on the first pass. Final C/W/A counts correct publications, wrong publications and abstentions. Trial tokens/correct charges all attempts and any metered answer-source tokens, including failures. All tokens/correct also charges the six preparation audit requests to each standalone method. Input, output, calls, model seconds and tool seconds in this table count trial work. Tool time includes non-model trial overhead. Charged seconds add trial wall time, per-trial scoring and the full shared preparation and calibration cost to each standalone method.", "",
             "| Language | Method | First C/P | Final C/W/A | Final published | Calls | Input | Output | Trial tokens/correct | All tokens/correct | Model s | Tool s | Trial wall s | Score s | Charged s |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for lang, arm in product(LANGUAGES, ARMS):
        s = summary[lang, arm]
        cost = tokens(s) / s['correct'] if s['correct'] else None
        trial_cost = (s['input'] + s['output']) / s['correct'] if s['correct'] else None
        lines.append(f"| {NAMES[lang]} | {NAMES[arm]} | {s['first_correct']}/{s['first_published']} | {s['correct']}/{s['wrong']}/{s['abstained']} | {s['published']} | {s['calls']} | {s['input']:,} | {s['output']:,} | {num(trial_cost)} | {num(cost)} | {s['model']:.2f} | {s['tool']:.2f} | {s['wall']:.2f} | {s['scoring']:.2f} | {setup+s['wall']+s['scoring']:.2f} |")
    all_rows = Counter()
    for s in summary.values():
        all_rows.update(s)
    lines.extend(["", f"Preparing {prep['acceptance_properties']} acceptance properties and {prep['labels']} example labels took {prep['wall_seconds']:.1f} elapsed seconds. The six shared Qwen mutation-audit calls added {workflow['audit_input']:,} input tokens, {workflow['audit_output']:,} output tokens and {workflow['audit_model']:.2f} model seconds ({audit_wall:.2f} s including checks). Public calibration took {public_cal:.2f} s and independent scorer calibration took {sealed_cal:.2f} s. Human minutes and development-author tokens were unmetered. {sensitivity(workflow, direct)}",
                  "", f"Across 90 assignments there were {all_rows['rejected']} candidate checks ending in rejection or abstention, {all_rows['retries']} model repair attempts and {all_rows['questions']} distinguishing questions. Authorized sources received {all_rows['authority_calls']} queries and supplied {all_rows['labels']} extra labels. Counting shared costs once gives {setup+all_rows['wall']+all_rows['scoring']:.2f} charged seconds for the study. [Decisions, prompts and receipts](decisions.jsonl) · [Closed independent scores](scores.json)",
                  "", "## Paired GPT++ decisions", "",
                  "Helped and hurt name the tasks on which only one method was independently correct. Ties are both correct / neither correct. Calls saved subtracts the left method’s calls from the comparator’s. The primary comparison is workflow versus one-call direct Qwen. The matched retry controls isolate the additional public counterexample in the retry prompt.", "",
                  "| Left method vs comparator | Helped | Hurt | Ties | Calls saved | Correctness Δ pp [95%] | Cost ratio [95%] | Undefined resamples |",
                  "|---|---|---|---:|---:|---:|---:|---:|"])
    for a, b in [("workflow", b) for b in ARMS[:-1]] + [("direct_witness", "direct_retry")]:
        left, right = groups["gpp", a], groups["gpp", b]
        w, l, both, neither, ci = compare(left, right, tasks)
        s, t = summary["gpp", a], summary["gpp", b]
        point = ratio(tokens(s), s['correct'], tokens(t), t['correct'])
        interval, unknown = bootstrap(left, right, tasks)
        interval_text = f"[{num(interval[0])}, {num(interval[1])}]" if interval else "[undefined]"
        lines.append(f"| {NAMES[a]} vs {NAMES[b]} | {', '.join(w) or '—'} | {', '.join(l) or '—'} | {both}/{neither} | {t['calls']-s['calls']} | {100*(len(w)-len(l))/len(tasks):+.1f} {ci_text(ci)} | {num(point)} {interval_text} | {100*unknown:.1f}% |")
    lines.extend(["", "The proposed engineering target requires a 95% lower correctness-difference bound of at least −2 percentage points and a 95% upper tokens-per-correct ratio of at most 0.80. The paired correctness interval subtracts simultaneous 97.5% exact binomial intervals for the win and loss probabilities (Bonferroni joint coverage ≥95%). The descriptive cost interval uses the 2.5th and 97.5th percentiles of all 46,656 ordered paired six-family bootstrap samples, charging each sampled family’s audit tokens to both methods. A zero success count or zero reference cost makes the cost ratio undefined. Undefined resamples widen the percentile bounds using their full possible range.",
                  "", "Six task families and one model leave the correctness margin unresolved. These measurements are inconclusive for the engineering target and for a language-wide advantage. Keep the workflow opt-in.",
                  "", "## Matched assignments by language", "", "Each cell gives final outcome/model calls. C denotes independently correct, W denotes a wrong publication, and A denotes abstention. All five conditions share each assignment’s edit scope, example labels and acceptance properties.", "",
                  "| Family | Language | Direct | Direct + blind retry | Direct + witness | Compiler only | Workflow |", "|---|---|---:|---:|---:|---:|---:|"])
    for task, lang in product(tasks, LANGUAGES):
        cells = []
        for arm in ARMS:
            s = groups[lang, arm][task]
            status = "C" if s["correct"] else "W" if s["wrong"] else "A"
            cells.append(f"{status}/{s['calls']}")
        lines.append("| " + " | ".join([task, NAMES[lang], *cells]) + " |")
    (output / "results.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    report(parser.parse_args().output)
