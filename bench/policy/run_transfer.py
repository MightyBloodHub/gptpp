"""Run and replay the historical upstream transfer with compiler-derived caller feedback."""

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time

import run_policy as study
from evaluate import arguments
from evaluate_project import ENTRY, MODULE
from obligation_feedback import obligation_text, public_obligation

HERE = study.HERE
DEV = HERE / "results/policy.jsonl"
HELPER = study.ROOT / "target/caller-obligation"


def selections():
    with DEV.open() as stream:
        meta = json.loads(next(stream))
        rows = [json.loads(line) for line in stream]
    roster = {(m, t, a) for m in study.MODELS for t in meta["tasks"] for a in study.ARMS}
    if len(rows) != len(roster) or {(r["model"], r["task"], r["condition"]) for r in rows} != roster:
        raise ValueError("Development run incomplete")
    selected = {}
    for model in study.MODELS:

        def rank(arm):
            group = [r for r in rows if (r["model"], r["condition"]) == (model, arm)]
            return (
                -sum(r["accepted"] for r in group),
                sum(a["input_tokens"] + a["output_tokens"] for r in group for a in r["attempts"]),
                arm,
            )

        selected[model] = {
            lang: min((arm for arm in study.ARMS if arm.startswith(lang + "_")), key=rank)
            for lang in ("gpp", "python", "rust")
        }
    return selected


def feedback(task, arm, source, previous):
    raw, detail, entry = previous
    lang, mode = arm.split("_")
    prompt, suffix = study.render(task, arm, source, (raw, detail))
    matching = [
        (fn, args, expected)
        for fn, args, expected in task["public"]
        if fn == entry and detail.startswith(f"{entry}({arguments(args, lang)}) ")
    ]
    if len(matching) != 1:
        raise ValueError(f"Cannot identify public failure {detail!r}")
    _, args, expected = matching[0]
    with TemporaryDirectory(prefix="caller-obligation-") as tmp:
        file = Path(tmp) / "caller.gpp"
        file.write_text(MODULE + study.source_for(task, "gpp") + ENTRY)
        note = public_obligation(
            HELPER, file, entry, task["target"], [str(v).lower() for v in args], expected
        )
    if note:
        prefix = "#" if lang == "python" or mode == "rules" else "//"

        def comment(text):
            return "".join(f"{prefix} {line}\n" for line in text.splitlines())

        decls = study.functions(source, lang)
        old = comment(
            study.maintenance.caller_context([fn.record() for fn in decls.values()], task["target"], lang)
        )
        if not old or prompt.count(old) != 1:
            raise ValueError("Ambiguous caller excerpt in rendered prompt")
        prompt = prompt.replace(old, comment(obligation_text(note)), 1)
    return prompt, suffix, note


def trial(tools, model, task, arm, defaults, replay=None):
    lang = arm.split("_")[0]
    source = study.source_for(task, lang)
    attempts, previous = [], None
    start = time.monotonic()
    hidden_ms, hidden_detail = 0, ""
    for index in range(2):
        note = None
        if previous:
            prompt, suffix, note = feedback(task, arm, source, previous)
        else:
            prompt, suffix = study.render(task, arm, source)
        began = time.monotonic()
        if replay is None:
            reply, options = study.generate(model, arm, prompt, suffix, defaults, retry=bool(index))
            record = dict(
                prompt=prompt,
                suffix=suffix,
                obligation=note,
                sampling=options,
                response=reply["response"],
                input_tokens=reply["prompt_eval_count"],
                output_tokens=reply["eval_count"],
                model_ms=study.pilot.elapsed(began),
                done_reason=reply["done_reason"],
            )
        else:
            record = dict(replay["attempts"][index])
            if (prompt, suffix, note) != (record["prompt"], record["suffix"], record["obligation"]):
                raise ValueError("Prompt or derived obligation changed")
        began = time.monotonic()
        raw = record["response"]
        status, detail, full = study.patch(tools, task, arm, source, raw)
        entry, stage = None, "patch"
        if status == "pass":
            stage = "public"
            status, detail, entry = study.previous.public_evaluate(tools, lang, full, task["public"])
        if replay is None:
            record["tool_ms"] = study.pilot.elapsed(began)
        record.update(
            public_outcome=status,
            public_detail=detail,
            stage=stage,
            public_failed_entry=entry,
            caller_context=bool(index) and note is None,
            outcome=status,
            patch_sha256=sha256(full.encode()).hexdigest() if full else None,
        )
        attempts.append(record)
        if status == "pass":
            began = time.monotonic()
            status, hidden_detail = study.evaluate(tools, lang, full, task["heldout"], already_checked=True)
            hidden_ms = study.pilot.elapsed(began)
            record["outcome"] = "accepted" if status == "pass" else "heldout_" + status
            break
        if not entry or entry == task["target"]:
            break
        previous = raw, detail, entry
    accepted = attempts[-1]["outcome"] == "accepted"
    row = dict(
        task=task["id"],
        model=model,
        seed=42,
        condition=arm,
        language=lang,
        kind="maintenance",
        form="body",
        accepted=accepted,
        first_accepted=accepted and len(attempts) == 1,
        attempts=attempts,
        wall_ms=study.pilot.elapsed(start) - hidden_ms,
        heldout_ms=hidden_ms,
        heldout_detail=hidden_detail,
    )
    if replay is not None:
        row.update(wall_ms=replay["wall_ms"], heldout_ms=replay["heldout_ms"])
        if row != replay:
            raise ValueError(f"Replay mismatch on {model} {task['id']} {arm}")
    return row


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--replay", action="store_true", help="rescore the archive without inference")
    args = parser.parse_args()
    from upstream import TASKS

    tools = study.Tools(study.ROOT, study.ROOT / "target/debug/gpp")
    tools.canaries()
    selected = selections()
    order = list(study.roster(TASKS))
    if args.replay:
        with args.output.open() as stream:
            info = json.loads(next(stream))
            rows = [json.loads(line) for line in stream]
        if (
            len(rows) != len(order)
            or selected != info["selected"]
            or info["corpus_sha256"]
            != sha256(json.dumps(TASKS, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            or info["gpp_sha256"] != study.pilot.digest(tools.gpp)
            or any(info["file_sha256"][f] != study.pilot.digest(study.ROOT / f) for f in info["file_sha256"])
        ):
            raise ValueError("Archive, dependencies or locked development selections changed")
        for (model, task, arm), row in zip(order, rows):
            trial(tools, model, task, arm, info["model_default_stops"][model], replay=row)
        print(f"Replayed {len(rows)} trials and {sum(len(r['attempts']) for r in rows)} completions")
        return
    info = study.manifest(tools, TASKS)
    info.update(
        study="historical-upstream-transfer-v8", selected=selected, development_sha256=study.pilot.digest(DEV)
    )
    for path in (
        HERE / "run_transfer.py",
        HERE / "transfer-protocol.md",
        HERE / "upstream.py",
        HERE / "upstream-sources.md",
        study.ROOT / "tools/obligation_feedback.py",
        study.ROOT / "tools/caller_obligation.rs",
        HELPER,
    ):
        info["file_sha256"][str(path.relative_to(study.ROOT))] = study.pilot.digest(path)
    if args.output.exists():
        with args.output.open() as stream:
            old = json.loads(next(stream))
            if any(old.get(k) != v for k, v in info.items()):
                raise ValueError("Cannot resume with changed inputs")
            rows = [json.loads(line) for line in stream]
    else:
        info["reference_cases_checked"] = study.maintenance.calibrate(tools, TASKS)
        info["started_at"] = datetime.now(timezone.utc).isoformat()
        with args.output.open("x") as stream:
            print(json.dumps(info), file=stream)
        rows = []
    if [(r["model"], r["task"], r["condition"]) for r in rows] != [
        (m, t["id"], a) for m, t, a in order[: len(rows)]
    ]:
        raise ValueError("Unexpected row order")
    with args.output.open("a", buffering=1) as stream:
        for i, (model, task, arm) in enumerate(order[len(rows) :], len(rows) + 1):
            row = trial(tools, model, task, arm, info["model_default_stops"][model])
            print(json.dumps(row, ensure_ascii=False), file=stream)
            print(f"{i}/{len(order)} {model} {task['id']} {arm} {row['attempts'][-1]['outcome']}", flush=True)


if __name__ == "__main__":
    main()
