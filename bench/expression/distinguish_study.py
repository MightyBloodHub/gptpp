"""Evaluate the disagreement CLI on frozen repair menus using additional oracle labels."""

import argparse
from datetime import date
from fractions import Fraction
from itertools import product
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time

import repair_study as prior


HERE, ROOT = prior.HERE, prior.ROOT
PARENT_ARCHIVE = HERE / "results/repair.jsonl"
PRODUCT = ROOT / "tools/distinguish.py"
POOLS = {
    "access_stamp": ([17, 501, 8388608, 16777210], [13, 713, 6811], [1, 1000]),
    "scale_channel": ([11, 37, 103, 169, 207, 241], [23, 59, 97, 151, 193, 237, 249, 253], [False, True]),
    "period_end": ([1964, 1973, 2037, 2176], [43567, 12700123, 28000567, 31000432]),
}


def oracle(target, args):
    if target == "access_stamp":
        clock, duration, multiplier = args
        for _ in range(duration * multiplier // 1000):
            clock = clock - 1 if clock else 16777214
        return clock
    if target == "scale_channel":
        level, fraction, mode = args
        return int(level * Fraction(fraction + int(mode), 256))
    if target == "period_end":
        year, elapsed = args
        year_end = (date(year + 1, 1, 1) - date(year, 1, 1)).days * 86400
        return next(x for x in (70 * 86400, 310 * 86400, year_end) if x > elapsed)
    raise ValueError(f"No independent answer rule for {target}.")


def probes_for(task):
    name = task["target"]
    pool = list(product(*POOLS[name]))
    # Compare named inputs only. Public and withheld expected values are never used for probes.
    previous = {tuple(case[1]) for case in [*task["public"], *task["heldout"]] if case[0] == name}
    if previous.intersection(pool):
        raise ValueError("An unlabeled probe overlaps a scored example.")
    return [{"function": name, "args": list(args)} for args in pool]


def evaluate(tools, task, menu):
    target = task["target"]
    probes = probes_for(task)
    original = prior.MODULE + prior.source_for(task, "gpp") + prior.ENTRY
    candidates = menu["candidates"]
    surviving = list(range(1, len(candidates) + 1))
    steps = []
    cli_ms = 0
    with TemporaryDirectory(prefix="gpp-question-study-") as directory:
        work = Path(directory)
        file, menu_file, probes_file = work / "base.gpp", work / "menu.json", work / "probes.json"
        file.write_text(original)
        menu_file.write_text(json.dumps(menu))
        probes_file.write_text(json.dumps(probes))
        while True:
            cmd = [sys.executable, "-B", PRODUCT, file, "--menu", menu_file, "--probes", probes_file,
                   "--gpp", prior.GPP]
            if len(surviving) != len(candidates):
                cmd.extend(["--candidates", ",".join(map(str, surviving))])
            start = time.monotonic()
            response = json.loads(subprocess.check_output(cmd, text=True, timeout=120))
            cli_ms += round((time.monotonic() - start) * 1000)
            if file.read_text() != original or response["revision"] != menu["revision"]:
                raise ValueError("Product changed the source or reported a different revision.")
            if response["candidate_count"] != len(surviving) or response["function"] != target:
                raise ValueError("Unexpected target or candidate subset.")
            step = {"starting_ids": surviving, "response": response}
            steps.append(step)
            question = response["question"]
            if response["status"] == "indistinguishable" and question is None:
                stop = "empty_menu" if not surviving else "single_candidate" if len(surviving) == 1 else "agree_on_pool"
                break
            if response["status"] != "question" or {"function": question["function"], "args": question["args"]} not in probes:
                raise ValueError("Tool returned an unexpected or unrequested call.")
            outcomes = question["outcomes"]
            if sorted(i for group in outcomes for i in group["candidates"]) != surviving or len(outcomes) < 2:
                raise ValueError("Question did not partition the full surviving set.")
            answer = oracle(question["function"], question["args"])
            step["oracle_result"] = answer
            surviving = next((o["candidates"] for o in outcomes if o.get("result") == answer), [])
            if not surviving:
                stop = "no_candidate_matches_oracle"
                break
        selected = surviving[0] if surviving else None
        score = {"outcome": stop}
        if selected is not None:
            candidate = candidates[selected - 1]
            fragment = work / "selected.expr"
            fragment.write_text(candidate["replacement"] + "\n")
            score = prior.score(tools, task, file, menu["revision"], candidate, fragment)
    return {"task": task["id"], "target": target, "menu_size": len(candidates), "pool": probes,
            "steps": steps, "stop": stop, "surviving_ids": surviving, "selected": selected,
            "score": score, "cli_ms": cli_ms}


def manifest():
    files = [Path(__file__).resolve(), PRODUCT, HERE / "distinguish-protocol.md"]
    return {"study": "repair-disagreement-followup-v1",
            "repair_archive_sha256": prior.fingerprint(PARENT_ARCHIVE.read_bytes()),
            "sources": {str(f.relative_to(ROOT)): prior.fingerprint(f.read_bytes()) for f in files}}


def run(path, replay):
    parent, records = prior.read_archive(PARENT_ARCHIVE)
    _, baseline = prior.baseline()
    prior.verify_rows(records, baseline)
    if parent["sources"] != prior.source_hashes():
        raise ValueError("Parent study dependencies changed.")
    meta = manifest()
    tools = prior.base.prior.Tools(ROOT, prior.GPP)
    saved_meta, saved = prior.read_archive(path) if replay else ({}, [])
    if replay and (saved_meta != meta or [r["task"] for r in saved] != [t["id"] for t in prior.TASKS]):
        raise ValueError("Follow-up provenance or roster changed.")
    results = []
    for index, task in enumerate(prior.TASKS):
        menus = [r["product"] for r in records if r["task"] == task["id"]]
        if any(m["revision"] != menus[0]["revision"] or m["candidates"] != menus[0]["candidates"] for m in menus):
            raise ValueError("The models had different menus in the original study.")
        row = evaluate(tools, task, menus[0])
        if replay:
            row["cli_ms"] = saved[index]["cli_ms"]
            if row != saved[index]:
                raise ValueError(f"Replay differed for {task['id']}.")
        results.append(row)
    if replay:
        print(f"Replayed {len(results)} tasks and verified choices, oracle labels and withheld outcomes.")
    else:
        with path.open("x") as stream:
            for record in [meta, *results]:
                print(json.dumps(record), file=stream)


def report(path):
    _, rows = prior.read_archive(path)
    print("# Choosing edits with distinguishing examples\n")
    print("A separate, oracle-assisted follow-up used each distinct task menu from the model study. "
          "The CLI received a fixed pool of fresh, unlabeled target inputs for each task. It asked for "
          "a label only when candidate predictions disagreed. This follow-up made zero model calls.\n")
    print("| Task | Menu size | Unlabeled inputs supplied | Extra oracle labels | Surviving IDs | Selected ID | Withheld result |")
    print("|---|---:|---:|---:|---|---:|---|")
    for row in rows:
        labels = [s for s in row["steps"] if "oracle_result" in s]
        print(f"| {row['task']} | {row['menu_size']} | {len(row['pool'])} | {len(labels)} | "
              f"{', '.join(map(str, row['surviving_ids'])) or '—'} | {row['selected'] or '—'} | {row['score']['outcome']} |")
    print()
    for row in rows:
        for step in row["steps"]:
            if "oracle_result" in step:
                q = step["response"]["question"]
                print(f"The tool asked for `{q['function']}({', '.join(json.dumps(a) for a in q['args'])})`. "
                      f"The independent specification oracle returned **{step['oracle_result']}**. "
                      "The predicted groups were " + ", ".join(
                          f"{o.get('result', o.get('fault'))} for IDs {o['candidates']}" for o in q['outcomes']) + ".\n")
    labels = sum("oracle_result" in s for r in rows for s in r["steps"])
    executions = sum(s["response"]["candidate_count"] * s["response"]["probes_tested"] for r in rows for s in r["steps"])
    passed = sum(r["score"]["outcome"] == "accepted" for r in rows)
    print(f"With {labels} additional oracle labels, the chosen patches passed all withheld cases on "
          f"{passed}/{len(rows)} development tasks. The CLI executed {executions} candidate/probe pairs in "
          f"{sum(r['cli_ms'] for r in rows) / 1000:.2f} seconds. The study scored only the final choices. "
          "Agreement on a finite pool leaves open the possibility of a difference on another input. "
          "Resolving a disagreement requires a reliable answer source. An empty menu leaves no edit to select. "
          "The earlier model-only outcomes remain a separate measurement.")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    action = cli.add_mutually_exclusive_group()
    action.add_argument("--replay", action="store_true")
    action.add_argument("--report", action="store_true")
    cli.add_argument("archive", type=Path)
    args = cli.parse_args()
    if args.report:
        report(args.archive)
    else:
        run(args.archive, args.replay)
