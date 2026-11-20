"""One paired alternate retry per exactly invertible first public caller failure in v7."""

import argparse
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import time

import run_transfer as transfer
from fresh import TASKS

study = transfer.study
ARCHIVE = study.HERE / "results/retry-obligations.jsonl"
REPORT = study.HERE / "results/retry-obligations.md"
PROTOCOL = study.HERE / "retry-obligations-protocol.md"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    with path.open() as stream:
        return json.loads(next(stream)), [json.loads(line) for line in stream]


def key(row):
    return row["model"], row["task"], row["condition"]


def load_design():
    meta, old = read(transfer.DEV)
    order = [(m, t["id"], a) for m, t, a in study.roster(TASKS)]
    require(len(order) == 112 and [key(row) for row in old] == order, "Incomplete or reordered v7 archive")
    for path, digest in meta["file_sha256"].items():
        require(study.pilot.digest(study.ROOT / path) == digest, f"Changed v7 dependency {path}")
    require(study.pilot.digest(study.ROOT / "target/debug/gpp") == meta["gpp_sha256"], "Compiler changed")
    corpus = sha256(json.dumps(TASKS, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    require(corpus == meta["corpus_sha256"], "Corpus changed")
    tasks = {task["id"]: task for task in TASKS}
    eligible, counts = [], Counter()
    for row in old:
        model, task_id, arm = key(row)
        task = tasks[task_id]
        first = row["attempts"][0]
        entry = first["public_failed_entry"]
        failed = (first["stage"] == "public" and first["public_outcome"] in ("wrong_answer", "runtime_error")
                  and entry is not None and entry != task["target"])
        require((len(row["attempts"]) == 2) == failed, "Archived retry does not follow the registered public gate")
        if not failed:
            counts[model, "no caller retry"] += 1
            continue
        source = study.source_for(task, row["language"])
        failure = first["response"], first["public_detail"]
        original, suffix = study.render(task, arm, source, failure)
        retry = row["attempts"][1]
        require((original, suffix) == (retry["prompt"], retry["suffix"]), "Cannot reproduce original retry input")
        prompt, protected, note = transfer.feedback(task, arm, source, (*failure, entry))
        require(suffix == protected, "Protected suffix changed")
        if note is None:
            require(prompt == original, "Unsupported obligation altered the retry")
            counts[model, "unsupported"] += 1
            continue
        require(note["status"] == "exact" and prompt != original, "Expected one exact caller fact")
        eligible.append((row, task, prompt, suffix, note))
        counts[model, "exact"] += 1
    return meta, old, eligible, counts


def manifest(meta, eligible, counts):
    paths = (Path(__file__).resolve(), PROTOCOL, study.HERE / "run_transfer.py",
             study.ROOT / "tools/caller_obligation.rs", study.ROOT / "tools/obligation_feedback.py", transfer.HELPER)
    return dict(study="v7-matched-caller-obligation-retry", development_sha256=study.pilot.digest(transfer.DEV),
                corpus_sha256=meta["corpus_sha256"], compiler_sha256=meta["gpp_sha256"],
                dependencies={str(p.relative_to(study.ROOT)): study.pilot.digest(p) for p in paths},
                model_digests=meta["model_digests"], model_default_stops=meta["model_default_stops"],
                selected=[list(key(row)) for row, *_ in eligible],
                counts={m: {k: counts[m, k] for k in ("no caller retry", "unsupported", "exact")}
                        for m in study.MODELS})


def judge(tools, task, arm, raw):
    lang = arm.split("_")[0]
    status, detail, full = study.patch(tools, task, arm, study.source_for(task, lang), raw)
    entry, stage = None, "patch"
    if status == "pass":
        stage = "public"
        status, detail, entry = study.previous.public_evaluate(tools, lang, full, task["public"])
    outcome, hidden = status, ""
    if status == "pass":
        status_hidden, hidden = study.evaluate(tools, lang, full, task["heldout"], already_checked=True)
        outcome = "accepted" if status_hidden == "pass" else "heldout_" + status_hidden
    return dict(outcome=outcome, heldout_detail=hidden, public_outcome=status, public_detail=detail, stage=stage,
                public_failed_entry=entry, patch_sha256=sha256(full.encode()).hexdigest() if full else None)


def controls(chosen):
    row, _, prompt, suffix, note = chosen
    model, task_id, arm = key(row)
    return dict(model=model, task=task_id, condition=arm, language=row["language"], prompt=prompt, suffix=suffix,
                obligation=note, sampling=row["attempts"][1]["sampling"],
                transport="raw-prefix-suffix-middle" if model == study.MODELS[1] else "ollama-native-suffix")


def collect(tools, meta, chosen):
    fields = controls(chosen)
    model, task_id, arm = key(fields)
    started = time.monotonic()
    reply, options = study.generate(model, arm, fields["prompt"], fields["suffix"],
                                    meta["model_default_stops"][model], retry=True)
    require(options == fields["sampling"] and reply["done"], f"Changed decoding options for {(model, task_id, arm)}")
    fields.update(response=reply["response"], model_ms=study.pilot.elapsed(started),
                  input_tokens=reply["prompt_eval_count"], output_tokens=reply["eval_count"],
                  done_reason=reply["done_reason"], load_ms=reply.get("load_duration", 0)/1e6,
                  generation_ms=reply.get("eval_duration", 0)/1e6)
    started = time.monotonic()
    fields.update(judge(tools, chosen[1], arm, fields["response"]))
    fields["evaluation_ms"] = study.pilot.elapsed(started)
    return fields


def report(old, rows, counts):
    updated = {key(r): r for r in rows}
    totals = {}
    for model in study.MODELS:
        group = [r for r in old if r["model"] == model]
        metrics = Counter()
        for r in group:
            alt = updated.get(key(r))
            original = r["attempts"]
            before = original[-1]
            after = alt or before
            metrics["total"] += 1
            metrics["old_accepted"] += r["accepted"]
            metrics["new_accepted"] += after["outcome"] == "accepted"
            for label, calls in [("old", original), ("new", original[:-1] + [after])]:
                metrics[label + "_cost"] += sum(a["input_tokens"] + a["output_tokens"] for a in calls)
            if alt:
                metrics["new_only"] += not r["accepted"] and alt["outcome"] == "accepted"
                metrics["old_only"] += r["accepted"] and alt["outcome"] != "accepted"
                for label, call in (("old", before), ("new", after)):
                    metrics[label + "_retry_accepted"] += call["outcome"] == "accepted"
                    for kind in ("input", "output"):
                        metrics[label + "_retry_" + kind] += call[kind + "_tokens"]
        totals[model] = metrics
    lines = ["# Same-failure caller retry comparison", "",
             "The alternate retry replaces the original caller source excerpt with an exact necessary leaf result. "
             "All 112 v7 first calls were screened using their public failures.", "",
             "| Model | Trials | First public caller failures | Exact retries | Unsupported |",
             "|---|---:|---:|---:|---:|"]
    for m, s in totals.items():
        e, u = counts[m, "exact"], counts[m, "unsupported"]
        lines.append(f"| {m} | {s['total']} | {e+u} | {e} | {u} |")
    lines.extend(["", "| Exact-retry cohort | Excerpt input / output tokens | Fact input / output tokens | "
                  "Accepted before / after | Gains / losses |", "|---|---:|---:|---:|---:|"])
    for m, s in totals.items():
        lines.append(f"| {m} | {s['old_retry_input']:,} / {s['old_retry_output']:,} | "
                     f"{s['new_retry_input']:,} / {s['new_retry_output']:,} | "
                     f"{s['old_retry_accepted']} / {s['new_retry_accepted']} | {s['new_only']} / {s['old_only']} |")
    lines.extend(["", "| Model, full workflow | Accepted before / after | Total tokens before / after | "
                  "Tokens per accepted edit before / after |", "|---|---:|---:|---:|"])
    for m, s in totals.items():
        rates = " / ".join(f"{s[k+'_cost']/s[k+'_accepted']:,.1f}" if s[k+'_accepted'] else "undefined"
                           for k in ("old", "new"))
        lines.append(f"| {m} | {s['old_accepted']} / {s['new_accepted']} | "
                     f"{s['old_cost']:,} / {s['new_cost']:,} | {rates} |")
    lines.extend(["", "The full-workflow calculation substitutes only the measured exact retries. "
                  "It retains the archived initial calls and every unsupported retry. "
                  "Per-model totals combine all seven arms; the same task appears in several arms. "
                  "Each model has one sample per eligible cell. These token and acceptance differences describe "
                  "the recorded failures on this corpus. [Protocol](../retry-obligations-protocol.md) · "
                  "[Paired retry archive](retry-obligations.jsonl) · [Original attempts](policy.jsonl)", ""])
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    for name in ("plan", "collect", "replay", "report"):
        mode.add_argument("--" + name, action="store_true")
    parser.add_argument("archive", nargs="?", type=Path, default=ARCHIVE)
    args = parser.parse_args()
    meta, old, chosen, counts = load_design()
    info = manifest(meta, chosen, counts)
    if args.plan:
        print(json.dumps({"assignments": len(old), "by_model": info["counts"]}, indent=2))
        return
    if args.archive.exists():
        header, rows = read(args.archive)
        header.pop("started_at")
        require(header == info, "Inputs or registered eligibility roster changed")
    elif args.collect:
        with args.archive.open("x") as stream:
            print(json.dumps(dict(info, started_at=datetime.now(timezone.utc).isoformat())), file=stream)
        rows = []
    else:
        parser.error("collect the comparison archive first")
    require([list(key(r)) for r in rows] == info["selected"][:len(rows)], "Unexpected retry roster or order")
    if args.report:
        require(len(rows) == len(chosen), "Comparison is incomplete")
        REPORT.write_text(report(old, rows, counts))
        print(REPORT)
        return
    tools = study.Tools(study.ROOT, study.ROOT / "target/debug/gpp")
    if args.replay:
        require(len(rows) == len(chosen), "Comparison is incomplete")
        for c, row in zip(chosen, rows):
            fields = controls(c)
            fields.update(judge(tools, c[1], row["condition"], row["response"]))
            require(all(row[k] == v for k, v in fields.items()), f"Replay discrepancy {key(row)}")
        print(f"Replayed all {len(rows)} exact obligation retries from {len(old)} assigned cells")
    elif len(rows) < len(chosen):
        tools.canaries()
        tags = {m["name"]: m["digest"] for m in study.pilot.request("tags")["models"]}
        require(all(tags[m] == d for m, d in info["model_digests"].items()), "Installed weights changed")
        with args.archive.open("a", buffering=1) as stream:
            for i, cell in enumerate(chosen[len(rows):], len(rows)+1):
                row = collect(tools, meta, cell)
                print(json.dumps(row, ensure_ascii=False), file=stream)
                print(f"{i}/{len(chosen)} {key(row)}", flush=True)


if __name__ == "__main__":
    main()
