"""Independently audit v8 upstream allocation, locked development choices, requests, usage and gates.

The program re-derives retry obligations using the pinned scalar analysis helper.
For sandboxed execution of archived completions use run_transfer.py --replay.
"""

import argparse
from collections import Counter, defaultdict
from hashlib import sha256
import json
from pathlib import Path
import random
import sys

import verify_policy as v7


FILES = "8da52e662dc4459e4387d827aed0123344fcb055685cfa6aab97c605c7adcc1f"
CORPUS = "80384800e1b9aef2b2914899f76bafb7d91b8518d9a84c925e5294f2f75c03cd"
DEVELOPMENT = "b2ea9858a751ab8addb170a754661004ded9596175fa8ce032e5bfaf724d0aeb"


def selection(path):
    v7.require(v7.audit.digest(path) == DEVELOPMENT, "frozen development archive differs")
    meta, *rows = map(json.loads, path.read_bytes().splitlines())
    v7.check_files(meta)
    order = v7.check_manifest(meta, v7.fixtures())
    v7.require([(r["model"], r["seed"], r["task"], r["condition"]) for r in rows] == order,
               "invalid development roster")
    wins, tokens = Counter(), Counter()
    for row in rows:
        key = row["model"], row["condition"]
        wins[key] += row["attempts"][-1]["outcome"] == "accepted"
        tokens[key] += sum(a["input_tokens"] + a["output_tokens"] for a in row["attempts"])
    result = {}
    for model in v7.MODELS:
        result[model] = {}
        for lang in ("gpp", "python", "rust"):
            choices = [a for m, a in wins if m == model and a.startswith(lang + "_")]
            result[model][lang] = min(choices, key=lambda arm: (-wins[model, arm], tokens[model, arm], arm))
    return result


def check_request(study, task, row, base, a, prior):
    import run_transfer as transfer
    model, arm = row["model"], row["condition"]
    if prior:
        failure = prior["response"], prior["public_detail"], prior["public_failed_entry"]
        prompt, suffix, obligation = transfer.feedback(task, arm, base, failure)
    else:
        prompt, suffix = study.render(task, arm, base)
        obligation = None
    v7.require((prompt, suffix, obligation) == (a["prompt"], a["suffix"], a["obligation"]),
               "retry obligation, prompt or suffix differs")
    v7.require(a["caller_context"] is (prior is not None and obligation is None), "wrong feedback selection")
    v7.check_wire(study, model, arm, prompt, suffix, a, prior is not None)


def check_gates(path, rows, meta, selected):
    report = path.read_text()
    models = v7.MODELS
    tasks = sorted(meta["tasks"])
    n = len(tasks)
    # The estimator resamples three paired upstream tasks. Identical sampled
    # multiplicities have identical metrics. Group them before pricing the tails.
    rng = random.Random(20261119)
    draws = Counter(tuple(sorted(rng.choices(tasks, k=n))) for _ in range(10000))
    records = {(r["model"], r["condition"], r["task"]): r for r in rows}
    for model in models:
        section = report.split("## " + model + "\n", 1)[1].split("\n## ", 1)[0].splitlines()
        primary = selected[model]["gpp"]
        for arm in (a for a in v7.ARMS if a != primary):
            pairs = {}
            for task in tasks:
                group = [records[model, a, task] for a in (primary, arm)]
                pairs[task] = [(r["accepted"], sum(a["input_tokens"] + a["output_tokens"] for a in r["attempts"]))
                               for r in group]
            delta, costs = [], []
            for draw, count in draws.items():
                (wins, spent), (base_wins, base_spent) = [
                    tuple(map(sum, zip(*(pairs[task][side] for task in draw)))) for side in (0, 1)
                ]
                delta.extend([100*(wins-base_wins)/n]*count)
                if wins and base_wins:
                    costs.extend([spent*base_wins/(base_spent*wins)]*count)
            delta.sort()
            costs.sort()
            missing = 10000-len(costs)
            full_success = [sum(p[side][0] for p in pairs.values()) for side in (0, 1)]
            intervals = (delta[249], delta[9749])
            text = next(s for s in section if s.startswith(f"| {arm} | {n}/{n} | {n} |"))
            cells = [v.strip() for v in text.strip("|").split("|")]
            v7.require(f"[{intervals[0]:.4f}, {intervals[1]:.4f}]" in cells[3], "acceptance interval differs")
            gate = "unestimable"
            if all(full_success):
                low = costs[249-missing] if missing <= 249 else 0
                high = costs[9749] if len(costs) > 9749 else float("inf")
                high_text = "∞" if high == float("inf") else f"{high:,.4f}"
                v7.require(f"[{low:,.4f}, {high_text}]" in cells[5], "cost interval differs")
                gate = "both bounds met" if intervals[0] >= -2 and high <= .8 else "bounds not both met"
            else:
                v7.require(cells[5] == "undefined", "undefined cost interval differs")
            v7.require(cells[-1] == gate, f"{model}/{arm}: gate decision differs")


def verify(log, dev, report, qwen, star):
    data = log.read_bytes()
    meta, *rows = map(json.loads, data.splitlines())
    v7.check_files(meta, "historical-upstream-transfer-v8", FILES)
    tasks = v7.fixtures("upstream")
    order = v7.check_manifest(meta, tasks, CORPUS, 3, (9, 52))
    v7.require([(r["model"], r["seed"], r["task"], r["condition"]) for r in rows] == order,
               "incomplete or reordered transfer assignment")
    selected = selection(dev)
    v7.require(meta["development_sha256"] == DEVELOPMENT and meta["selected"] == selected,
               "development selections differ")
    import run_policy as study
    encoders = v7.tokenizers(qwen, star)
    totals = defaultdict(Counter)
    by_name = {t["id"]: t for t in tasks}
    for row in rows:
        task, arm, model = by_name[row["task"]], row["condition"], row["model"]
        base = study.source_for(task, row["language"])
        try:
            v7.prior.check_public_reachability(study.previous, task, row["language"], base)
            v7.check_trial(study, task, row, base, check_request, durations=())
            c = totals[model, arm]
            c["assigned"] += 1
            c["accepted"] += row["accepted"]
            c["first"] += row["first_accepted"]
            c["first_tokens"] += sum(row["attempts"][0][k] for k in ("input_tokens", "output_tokens"))
            c["wall_ms"] += row["wall_ms"]
            for a in row["attempts"]:
                c["calls"] += 1
                c["obligations"] += a["obligation"] is not None
                c["input"] += a["input_tokens"]
                c["output"] += a["output_tokens"]
                if model in encoders:
                    installed, released = encoders[model]
                    text = v7.serialized(model, a["prompt"], a["suffix"])
                    n = len(installed.encode(text).ids)
                    v7.require(min(n, 2048) == a["input_tokens"], "independent input count differs")
                    c["retokenized"] += 1
                    c["truncated"] += n > 2048
                    if model == v7.STAR:
                        upstream = len(released.encode(text).ids)
                        c["publisher_tokens"] += upstream
                        c["publisher_differences"] += n != upstream
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError(f"{model}/{task['id']}/{arm}: {exc}") from exc
    if report:
        v7.check_report(log, report, totals, selected)
        check_gates(report, rows, meta, selected)
    v7.require(log.read_bytes() == data, "archive changed during verification")
    for model in v7.MODELS:
        print(f"{model} selected {selected[model]}")
        for arm in v7.ARMS:
            c = totals[model, arm]
            print(f"  {arm}: {c['accepted']}/{c['assigned']} accepted, {c['calls']} calls, "
                  f"{c['input']+c['output']} total tokens, {c['obligations']} exact obligations")
        print(f"  all arms {dict(sum((totals[model, arm] for arm in v7.ARMS), Counter()))}")
    total = sum(totals.values(), Counter())
    print(f"Verified {total['assigned']} transfer assignments, {total['calls']} requests and "
          f"{total['accepted']} accepts. Archive SHA-256 {sha256(data).hexdigest()}")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("log", type=Path)
    cli.add_argument("--development", type=Path, default=v7.HERE / "results/policy.jsonl")
    cli.add_argument("--report", type=Path)
    cli.add_argument("--qwen-tokenizer", type=Path)
    cli.add_argument("--star-tokenizer", type=Path)
    args = cli.parse_args()
    try:
        verify(args.log, args.development, args.report, args.qwen_tokenizer, args.star_tokenizer)
    except (TypeError, KeyError, ValueError, OSError, ImportError) as exc:
        cli.exit(1, f"{exc}\n")
