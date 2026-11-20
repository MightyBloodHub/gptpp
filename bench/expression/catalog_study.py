"""Run, replay or summarize the one-call compiler catalog development follow-up."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import random
import time

import run_expression as base
from bench.expression.tasks import TASKS
from indexed_edit import edit_request, order_spans, read_change
from report_expression import Measurement, paired, pretty, table

DATA = base.HERE / "results/expression.jsonl"
SEED = 30992


def assignments():
    for model in base.prior.MODELS:
        pairs = [(task, lang) for task in TASKS for lang in base.LANGUAGES]
        random.Random(SEED).shuffle(pairs)
        for task, lang in pairs:
            yield model, task, lang


def config():
    lines = DATA.read_bytes().splitlines()
    meta = json.loads(lines[0])
    if len(lines) != len(TASKS) * len(meta["models"]) * len(meta["conditions"]) + 1:
        raise ValueError("Complete the original study before starting the follow-up.")
    for path, digest in meta["file_sha256"].items():
        if base.prior.pilot.digest(base.ROOT / path) != digest:
            raise ValueError(f"Original study source changed: {path}")
    if (
        base.prior.pilot.digest(base.ROOT / "target/debug/gpp") != meta["gpp_sha256"]
        or base.prior.pilot.digest(base.RUST_PARSER) != meta["rust_parser_sha256"]
    ):
        raise ValueError("A checked editing adapter changed since the original study.")
    names = [
        Path(__file__),
        base.HERE / "catalog-protocol.md",
        base.ROOT / "tools/indexed_edit.py",
        base.HERE.parent / "iterate/report.py",
        base.HERE.parent / "empirical/summarize.py",
    ]
    return dict(
        study="catalog-followup-v9",
        original_archive_sha256=base.prior.pilot.digest(DATA),
        sources={str(p.relative_to(base.ROOT)): base.prior.pilot.digest(p) for p in names},
        model_digests=meta["model_digests"],
        order_seed=SEED,
        gpp_sha256=base.prior.pilot.digest(base.ROOT / "target/debug/gpp"),
        rust_parser_sha256=base.prior.pilot.digest(base.RUST_PARSER),
    )


def trial(tools, model, task, language, saved=None):
    start = time.monotonic()
    source = base.prior.source_for(task, language)
    target = base.sites.function_text(task, language, source)
    spans = order_spans(base.sites.catalog(tools, base.RUST_PARSER, task, language, source))
    examples = [f"{name}({base.arguments(args, language)}) = {want}" for name, args, want in task["public"]]
    payload = edit_request(model, language, task["description"], examples, target, spans)
    if saved:
        if payload != saved["request"]:
            raise ValueError("Catalog request differs from the archive.")
        reply, model_ms = saved["reply"], saved["model_ms"]
    else:
        began = time.monotonic()
        generated = base.prior.pilot.request("generate", payload)
        model_ms = base.prior.pilot.elapsed(began)
        if generated.get("done") is not True:
            raise RuntimeError("Generation did not finish.")
        reply = {k: generated[k] for k in ("response", "done_reason", "prompt_eval_count", "eval_count")}
    fields = {}
    try:
        span, fragment = read_change(reply["response"], spans)
        fields["span"] = list(span)
        status, detail, patch = base.sites.apply(
            tools, base.RUST_PARSER, task, language, source, span, fragment
        )
        if status == "pass":
            fields["patch_sha256"] = sha256(patch.encode()).hexdigest()
            status, detail, _ = base.prior.previous.public_evaluate(tools, language, patch, task["public"])
        if status == "pass":
            status, detail = base.prior.evaluate(
                tools, language, patch, task["heldout"], already_checked=True
            )
            status = "accepted" if status == "pass" else "heldout_" + status
    except (ValueError, RecursionError) as exc:
        status, detail = "selection_error", str(exc)
    row = dict(
        model=model,
        language=language,
        task=task["id"],
        request=payload,
        reply=reply,
        model_ms=model_ms,
        wall_ms=saved["wall_ms"] if saved else base.prior.pilot.elapsed(start),
        outcome=status,
        detail=detail,
        **fields,
    )
    if saved and row != saved:
        raise ValueError(f"Catalog outcome differs for {model}/{task['id']}/{language}")
    return row


def read(path):
    with path.open() as stream:
        return json.loads(next(stream)), [json.loads(line) for line in stream]


def run(path, replay):
    tools = base.prior.Tools(base.ROOT, base.ROOT / "target/debug/gpp")
    tools.canaries()
    setup = config()
    if not replay:
        installed = {m["name"]: m["digest"] for m in base.prior.pilot.request("tags")["models"]}
        if any(installed.get(name) != digest for name, digest in setup["model_digests"].items()):
            raise ValueError("A model differs from the original study.")
    order = list(assignments())
    if path.exists():
        meta, rows = read(path)
        if meta != setup or [(r["model"], r["task"], r["language"]) for r in rows] != [
            (m, t["id"], lang) for m, t, lang in order[: len(rows)]
        ]:
            raise ValueError("Follow-up manifest or roster changed.")
    elif replay:
        raise ValueError("Missing follow-up archive.")
    else:
        rows = []
        with path.open("x") as stream:
            print(json.dumps(setup), file=stream)
    if replay:
        if len(rows) != len(order):
            raise ValueError("Replay needs all trials.")
        for assignment, row in zip(order, rows):
            trial(tools, *assignment, row)
        print(f"Replayed {len(rows)} catalog-guided changes")
        return
    with path.open("a", buffering=1) as stream:
        for assignment in order[len(rows) :]:
            row = trial(tools, *assignment)
            print(json.dumps(row), file=stream)
            print(row["model"], row["task"], row["language"], row["outcome"], flush=True)


def report(path):
    meta, rows = read(path)
    if meta["original_archive_sha256"] != base.prior.pilot.digest(DATA):
        raise ValueError("The comparison archive has changed.")
    expected = {(m, t["id"], lang) for m, t, lang in assignments()}
    observed = {(r["model"], r["task"], r["language"]) for r in rows}
    if expected != observed or len(rows) != len(expected):
        raise ValueError("Need the complete follow-up roster.")
    _, original = read(DATA)
    print("# Catalog-guided expression edits")
    print(
        f"\n{len(rows)} fresh model calls on the three v9 development tasks. Every request includes the "
        "target, the public examples and the selectable expression list. Counts include every failed call."
    )
    for model in base.prior.MODELS:
        print("\n## " + model)
        samples, lines = {}, []
        for lang in base.LANGUAGES:
            group = [r for r in rows if r["model"] == model and r["language"] == lang]
            inputs = sum(r["reply"]["prompt_eval_count"] for r in group)
            outputs = sum(r["reply"]["eval_count"] for r in group)
            successes = sum(r["outcome"] == "accepted" for r in group)
            # Grammar is supplied via Ollama's format field outside the text prompt.
            grammar_bytes = sum(
                len(json.dumps(r["request"]["format"], separators=(",", ":")).encode()) for r in group
            )
            lines.append(
                [
                    lang,
                    sum("span" in r for r in group),
                    f"{successes}/{len(group)}",
                    inputs,
                    outputs,
                    pretty((inputs + outputs) / successes if successes else None),
                    grammar_bytes,
                ]
            )
            for r in group:
                usage = r["reply"]["prompt_eval_count"] + r["reply"]["eval_count"]
                samples[model, 42, r["task"], lang + "_catalog"] = Measurement(
                    r["task"], r["outcome"] == "accepted", usage, 0
                )
        table(
            [
                "Language",
                "Valid sites",
                "Accepted",
                "Input tokens",
                "Output tokens",
                "Tokens/accept",
                "Decoder schema bytes",
            ],
            lines,
        )
        for r in original:
            if r["model"] == model:
                usage = sum(
                    a["input_tokens"] + a["output_tokens"] for a in r["attempts"] if a["stage"] != "retry"
                )
                samples[model, 42, r["task"], r["condition"]] = Measurement(
                    r["task"], r["first_accepted"], usage, 0
                )
        lines = []
        for comp in (
            "python_catalog",
            "rust_catalog",
            "gpp_locate",
            "gpp_combined",
            "python_full",
            "rust_full",
        ):
            _, _, _, delta, _, ratio, _, gate = paired(samples, comp, len(TASKS), "gpp_catalog", True)
            lines.append([comp, delta, ratio, gate])
        table(
            [
                "Comparator for GPT++ catalog",
                "Acceptance difference, pp [95% interval]",
                "Tokens/accept ratio [95% interval]",
                "Gate",
            ],
            lines,
        )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    modes = cli.add_mutually_exclusive_group()
    modes.add_argument("--replay", action="store_true")
    modes.add_argument("--report", action="store_true")
    cli.add_argument("archive", type=Path)
    args = cli.parse_args()
    if args.report:
        report(args.archive)
    else:
        run(args.archive, args.replay)
