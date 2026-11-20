"""Run or replay a paired benchmark of in-function expression localization and editing."""

import argparse
from collections import deque
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import random
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent / "policy"))
import run_policy as prior
from evaluate import arguments
from propose import ProposalError, combined_prompt, expression_context, location_prompt, parse_change
import sites

RUST_PARSER = ROOT / "target/expr-rust-syntax/debug/expression-bench-rust-syntax"
LANGUAGES = ("gpp", "python", "rust")
MODES = ("full", "given", "locate", "combined")
ARMS = tuple(f"{lang}_{mode}" for lang in LANGUAGES for mode in MODES)
ORDER_SEED = 30991


def assignments(tasks):
    for model in prior.MODELS:
        rng = random.Random(ORDER_SEED)
        ordered = tasks.copy()
        rng.shuffle(ordered)
        for task in ordered:
            arms = list(ARMS)
            rng.shuffle(arms)
            for arm in arms:
                yield model, task, arm


def options(model, lang, stage, defaults):
    stops = defaults + (prior.STAR_STOPS if model == prior.MODELS[1] else []) + prior.previous.STOPS[lang]
    if stage == "location":
        stops = stops + ["\n"]
    result = dict(prior.pilot.OPTIONS, stop=list(dict.fromkeys(stops)))
    if stage == "retry":
        result.update(seed=43, temperature=0.25)
    return result


def request(model, prompt, suffix, settings):
    payload = dict(model=model, options=settings, stream=False, keep_alive="3m")
    if model == prior.MODELS[1]:
        payload.update(raw=True, prompt=f"<fim_prefix>{prompt}<fim_suffix>{suffix}<fim_middle>")
    else:
        payload.update(prompt=prompt, suffix=suffix)
    return prior.pilot.request("generate", payload)


def trial(tools, task, model, arm, defaults, replay=None):
    lang, mode = arm.split("_")
    source = prior.source_for(task, lang)
    text = sites.function_text(task, lang, source)
    examples = [f"{name}({arguments(args, lang)}) = {expected}" for name, args, expected in task["public"]]
    comment = "#" if lang == "python" else "//"
    calls = []
    archive = deque(replay["attempts"]) if replay else None
    start = time.monotonic()

    def call(stage, prompt, suffix):
        settings = options(model, lang, stage, defaults)
        record = dict(stage=stage, prompt=prompt, suffix=suffix, sampling=settings)
        if archive is None:
            began = time.monotonic()
            reply = request(model, prompt, suffix, settings)
            record.update(
                response=reply["response"],
                done_reason=reply["done_reason"],
                input_tokens=reply["prompt_eval_count"],
                output_tokens=reply["eval_count"],
                model_ms=prior.pilot.elapsed(began),
            )
        else:
            saved = archive.popleft()
            if any(saved[key] != value for key, value in record.items()):
                raise ValueError(f"Request differed on {task['id']}/{model}/{arm}/{stage}")
            for key in ("response", "done_reason", "input_tokens", "output_tokens", "model_ms"):
                record[key] = saved[key]
        calls.append(record)
        return record

    span, failure, accepted, first = None, [], False, False
    change = None
    if mode != "full":
        ranges = sites.catalog(tools, RUST_PARSER, task, lang, source)
        if mode == "given":
            span = sites.resolve(text, ranges, task["site"][lang])
        elif mode == "locate":
            prompt, suffix = location_prompt(task["description"], examples, text, comment)
            location = call("location", prompt, suffix)
            try:
                span = sites.resolve(text, ranges, location["response"])
                location.update(outcome="located", detail="")
            except ValueError as exc:
                location.update(outcome="selection_error", detail=str(exc))
        else:
            prompt, suffix = combined_prompt(task["description"], examples, text, comment)
            change = call("change", prompt, suffix)
            try:
                old, fragment = parse_change(change["response"])
                span = sites.resolve(text, ranges, old)
                change.update(located=True, old=old, fragment=fragment)
            except (ProposalError, ValueError) as exc:
                change.update(outcome="selection_error", detail=str(exc), located=False)
    if mode == "full" or span is not None:
        for index in range(2):
            if change is not None and index == 0:
                record, raw = change, change["fragment"]
            else:
                if mode == "full":
                    prompt, suffix = prior.render(task, arm, source, (raw, diagnostic) if index else None)
                else:
                    a, b = span
                    data = text.encode()
                    old = data[a:b].decode()
                    context = expression_context(task["description"], examples, old, failure)
                    prompt = (
                        "".join(f"{comment} {line}\n" for line in context.splitlines()) + data[:a].decode()
                    )
                    suffix = data[b:].decode() + "\n"
                record = call("retry" if index else "edit", prompt, suffix)
                raw = record["response"]
            if mode == "full":
                status, diagnostic, patched = prior.patch(tools, task, arm, source, raw)
            else:
                status, diagnostic, patched = sites.apply(tools, RUST_PARSER, task, lang, source, span, raw)
            entry = None
            if status == "pass":
                status, diagnostic, entry = prior.previous.public_evaluate(
                    tools, lang, patched, task["public"]
                )
            record.update(
                public_outcome=status,
                public_detail=diagnostic,
                public_failed_entry=entry,
                patch_sha256=sha256(patched.encode()).hexdigest() if patched else None,
                outcome=status,
            )
            if status == "pass":
                hidden, detail = prior.evaluate(tools, lang, patched, task["heldout"], already_checked=True)
                accepted = hidden == "pass"
                first = accepted and not index
                record.update(outcome="accepted" if accepted else "heldout_" + hidden, hidden_detail=detail)
                break
            if not entry or entry == task["target"] or index:
                break
            decls = prior.functions(source, lang)
            excerpt = prior.maintenance.caller_context(
                [fn.record() for fn in decls.values()], task["target"], lang
            )
            failure = ["Previous insertion", raw, diagnostic, excerpt]
    row = dict(
        model=model,
        task=task["id"],
        language=lang,
        condition=arm,
        seed=42,
        kind="maintenance",
        span=list(span) if span else None,
        accepted=accepted,
        first_accepted=first,
        attempts=calls,
        wall_ms=replay["wall_ms"] if replay else prior.pilot.elapsed(start),
    )
    if replay and (archive or row != replay):
        raise ValueError(f"Outcome differed on {task['id']}/{model}/{arm}")
    return row


def calibrate(tools, tasks):
    count = prior.maintenance.calibrate(tools, tasks)
    for task in tasks:
        for lang in LANGUAGES:
            source = prior.source_for(task, lang)
            text = sites.function_text(task, lang, source)
            ranges = sites.catalog(tools, RUST_PARSER, task, lang, source)
            span = sites.resolve(text, ranges, task["site"][lang])
            status, detail, patch = sites.apply(
                tools, RUST_PARSER, task, lang, source, span, task["fix"][lang]
            )
            if status == "pass":
                status, detail = prior.evaluate(tools, lang, patch, task["public"] + task["heldout"])
            if status != "pass":
                raise ValueError(f"Known expression edit failed on {task['id']}/{lang}: {detail}")
    return count


def manifest(tools, tasks):
    info = prior.manifest(tools, tasks)
    for file in (
        HERE / "run_expression.py",
        HERE / "report_expression.py",
        HERE / "sites.py",
        HERE / "protocol.md",
        HERE / "tasks.py",
        HERE / "sources.md",
        HERE / "rust_syntax/Cargo.toml",
        HERE / "rust_syntax/Cargo.lock",
        HERE / "rust_syntax/src/main.rs",
        ROOT / "tools/propose.py",
    ):
        info["file_sha256"][str(file.relative_to(ROOT))] = prior.pilot.digest(file)
    info.update(
        study="upstream-expression-maintenance-v9",
        primary="gpp_locate",
        primary_comparator="python_locate",
        secondary="gpp_combined",
        conditions=list(ARMS),
        order_seed=ORDER_SEED,
        rust_parser_sha256=prior.pilot.digest(RUST_PARSER),
    )
    return info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--replay", action="store_true")
    args = parser.parse_args()
    from bench.expression.tasks import TASKS

    tools = prior.Tools(ROOT, ROOT / "target/debug/gpp")
    tools.canaries()
    order = list(assignments(TASKS))
    rows = []
    if args.archive.exists():
        with args.archive.open() as stream:
            info = json.loads(next(stream))
            rows = [json.loads(line) for line in stream]
        if [(r["model"], r["task"], r["condition"]) for r in rows] != [
            (m, t["id"], a) for m, t, a in order[: len(rows)]
        ]:
            raise ValueError("Archive diverges from the assignment roster")
    if args.replay:
        if not args.archive.exists() or len(rows) != len(order):
            raise ValueError("Replay requires a complete archive")
        fingerprint = sha256(json.dumps(TASKS, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if (
            fingerprint != info["corpus_sha256"]
            or prior.pilot.digest(tools.gpp) != info["gpp_sha256"]
            or prior.pilot.digest(RUST_PARSER) != info["rust_parser_sha256"]
        ):
            raise ValueError("Corpus or executable changed since scoring")
        for path, digest in info["file_sha256"].items():
            if prior.pilot.digest(ROOT / path) != digest:
                raise ValueError(f"Source fingerprint differs: {path}")
        for (model, task, arm), row in zip(order, rows):
            trial(tools, task, model, arm, info["model_default_stops"][model], row)
        print(f"Replayed {len(rows)} trials and {sum(len(r['attempts']) for r in rows)} calls")
        return
    settings = manifest(tools, TASKS)
    if args.archive.exists():
        if any(info.get(k) != v for k, v in settings.items()):
            raise ValueError("Cannot resume across a changed manifest")
    else:
        settings["reference_cases_checked"] = calibrate(tools, TASKS)
        settings["started_at"] = datetime.now(timezone.utc).isoformat()
        with args.archive.open("x") as stream:
            print(json.dumps(settings), file=stream)
    with args.archive.open("a", buffering=1) as stream:
        for i, (model, task, arm) in enumerate(order[len(rows) :], len(rows) + 1):
            row = trial(tools, task, model, arm, settings["model_default_stops"][model])
            print(json.dumps(row, ensure_ascii=False), file=stream)
            print(
                f"{i}/{len(order)} {model} {task['id']} {arm}: {row['attempts'][-1]['outcome']}", flush=True
            )


if __name__ == "__main__":
    main()
