"""Test every frozen GPT++ reply against the compiler with native conversions and integer intrinsics."""

import argparse
from itertools import product
import json
from pathlib import Path

import agent_study as study
import agent_fresh_tasks as fresh
from indexed_edit import order_spans, read_change


HERE, ROOT = study.HERE, study.ROOT
BLOCKS = (("historical", HERE / "results/agent.jsonl", study.prior.TASKS),
          ("arithmetic", HERE / "results/fresh-agent.jsonl", fresh.TASKS))


def extra_cases(task):
    name = task["target"]
    if name == "adjust":
        xs = (-1000, -101, -100, -99, -2, -1, 0, 1, 2, 99, 100, 101, 1000)
        args, oracle = product(xs, repeat=2), fresh.clamp
    elif name == "delay_ticks":
        xs = {i + d for i in range(0, 100001, 1000) for d in (-1, 0, 1, 999) if i + d >= 0}
        args, oracle = ((x,) for x in sorted(xs | {9999999, 10000000})), fresh.ticks
    elif name == "in_window":
        xs = (-1000, -101, -5, -1, 0, 1, 4, 73, 1000)
        args = ((p, a, b) for p, a, b in product(xs, repeat=3) if a <= b)
        oracle = fresh.inside
    else:
        return []
    return [(name, a, oracle(*a)) for a in args]


def score(tools, task, source, spans, recorded):
    raw = recorded["reply"]["response"]
    row = {"response_sha256": study.prior.fingerprint(raw.encode()), "original_public": recorded["status"]}
    try:
        span, expression = read_change(raw, spans)
    except ValueError as exc:
        if recorded["span"] is not None:
            raise
        return {**row, "public": "invalid_selection", "detail": str(exc), "outcome": "invalid_selection"}, None
    if list(span) != recorded["span"] or expression != recorded["replacement"]:
        raise ValueError("Reconstructed edit differs from the frozen model answer.")
    row.update(span=list(span), expression=expression)
    outcome, detail, patch = study.catalog.base.sites.apply(tools, None, task, "gpp", source, span, expression)
    if patch:
        row["patch_sha256"] = study.prior.fingerprint((study.MODULE + patch + study.ENTRY).encode())
        if recorded["patch_sha256"] is not None and row["patch_sha256"] != recorded["patch_sha256"]:
            raise ValueError("Previously type-correct edit changed its source bytes.")
    if outcome == "pass":
        outcome, detail = study.evaluate(tools, "gpp", patch, task["public"])
    row["public"] = outcome
    if outcome == "pass":
        held, detail = study.evaluate(tools, "gpp", patch, task["heldout"], already_checked=True)
        outcome = "accepted" if held == "pass" else "withheld_" + held
    return {**row, "detail": detail, "outcome": outcome}, patch


def trial(tools, name, file, task, record):
    source = study.source_for(task, "gpp")
    spans = order_spans(study.catalog.base.sites.catalog(tools, None, task, "gpp", source))
    rows = []
    chosen, accepted_patch = None, None
    for i, answer in enumerate(record["attempts"], 1):
        result, patch = score(tools, task, source, spans, answer)
        rows.append(result)
        if chosen is None and result["public"] == "pass":
            chosen = i
            if result["outcome"] == "accepted":
                accepted_patch = patch
    extra = []
    if accepted_patch:
        extra = extra_cases(task)
        for offset in range(0, len(extra), 64):
            result, detail = study.evaluate(tools, "gpp", accepted_patch, extra[offset:offset+64])
            if result != "pass":
                raise ValueError(f"Extended checks failed for {task['id']}: {detail}")
    return {"block": name, "source_archive": str(file.relative_to(ROOT)), "model": record["model"],
            "task": task["id"], "original_outcome": record["outcome"], "attempts": rows, "chosen": chosen,
            "outcome": rows[(chosen or len(rows))-1]["outcome"], "extra_direct_checks_passed": len(extra),
            "charged_input_tokens": sum(a["reply"]["prompt_eval_count"] for a in record["attempts"]),
            "charged_output_tokens": sum(a["reply"]["eval_count"] for a in record["attempts"])}


def generate(gpp):
    sources = [Path(__file__).resolve(), HERE / "compat-protocol.md", HERE / "agent_fresh_tasks.py",
               *sorted((ROOT / "src").glob("*.rs"))]
    meta = {"study": "frozen-native-compatibility-v1",
            "archives": {str(f.relative_to(ROOT)): study.prior.fingerprint(f.read_bytes()) for _, f, _ in BLOCKS},
            "sources": {str(f.relative_to(ROOT)): study.prior.fingerprint(f.read_bytes()) for f in sources},
            "gpp_sha256": study.prior.fingerprint(gpp.read_bytes())}
    tools = study.catalog.base.prior.Tools(ROOT, gpp)
    result = []
    for name, file, tasks in BLOCKS:
        _, rows = study.prior.read_archive(file)
        expected = {(m, t["id"]) for m in study.catalog.base.prior.MODELS for t in tasks}
        group = [r for r in rows if r["language"] == "gpp"]
        if len(group) != len(expected) or {(r["model"], r["task"]) for r in group} != expected:
            raise ValueError("Incomplete original GPT++ roster.")
        by_id = {t["id"]: t for t in tasks}
        result.extend(trial(tools, name, file, by_id[r["task"]], r) for r in group)
    return meta, result


def report(path):
    _, rows = study.prior.read_archive(path)
    print("# Frozen GPT++ expressions on the extended language\n")
    print("The compiler now accepts explicit Boolean-to-integer conversion and checked integer minimum, "
          "maximum and clamp operations. These features were chosen after inspecting the original model "
          "failures. This retrospective used the original site IDs, expressions and source programs and "
          "made zero new model calls. All original tokens remain charged.\n")
    print("| Task block | Model | Before | First answers now accepted | Final accepted | Charged input | Charged output | Tokens/accept |")
    print("|---|---|---:|---:|---:|---:|---:|---:|")
    for block, model in dict.fromkeys((r["block"], r["model"]) for r in rows):
        g = [r for r in rows if (r["block"], r["model"]) == (block, model)]
        old = sum(r["original_outcome"] == "accepted" for r in g)
        first = sum(r["attempts"][0]["outcome"] == "accepted" for r in g)
        solved = sum(r["outcome"] == "accepted" for r in g)
        inputs, outputs = sum(r["charged_input_tokens"] for r in g), sum(r["charged_output_tokens"] for r in g)
        cost = f"{(inputs+outputs)/solved:,.1f}" if solved else "undefined"
        print(f"| {block} | {model} | {old}/{len(g)} | {first}/{len(g)} | {solved}/{len(g)} | "
              f"{inputs:,} | {outputs:,} | {cost} |")
    print("\n| Model | Task | Selected attempt | Final outcome | Additional direct checks passed |")
    print("|---|---|---:|---|---:|")
    for r in rows:
        print(f"| {r['model']} | {r['task']} | {r['chosen'] or '—'} | {r['outcome']} | {r['extra_direct_checks_passed']} |")
    print("\nThe comparison uses familiar spellings present in the material that motivated the change. "
          "It measures compiler compatibility with those saved proposals. It leaves open whether fresh "
          "models choose effective repairs on independent tasks or use fewer tokens than Python or Rust.")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    modes = cli.add_mutually_exclusive_group()
    modes.add_argument("--report", action="store_true")
    modes.add_argument("--replay", action="store_true")
    cli.add_argument("--gpp", type=Path, default=study.GPP)
    cli.add_argument("archive", type=Path)
    args = cli.parse_args()
    if args.report:
        report(args.archive)
    else:
        meta, rows = generate(args.gpp.resolve(strict=True))
        if args.replay:
            prior_meta, prior_rows = study.prior.read_archive(args.archive)
            # Native executable layout varies across equivalent checkouts. Compare source and outcomes.
            if {k:v for k,v in prior_meta.items() if k != "gpp_sha256"} != {k:v for k,v in meta.items() if k != "gpp_sha256"} or rows != prior_rows:
                raise ValueError("Retrospective request, source or outcome changed.")
            print(f"Replayed {sum(len(r['attempts']) for r in rows)} frozen expressions.")
        else:
            with args.archive.open("x") as stream:
                for entry in [meta, *rows]:
                    print(json.dumps(entry), file=stream)
