"""Run, replay or report the three new arithmetic tasks with the frozen agent workflow."""

import argparse
import json
from pathlib import Path
import random
import shutil
from tempfile import TemporaryDirectory

import agent_study as study
from agent_fresh_tasks import TASKS


def roster():
    for model in study.catalog.base.prior.MODELS:
        block = [(t, lang) for t in TASKS for lang in ("gpp", "python", "rust")]
        random.Random(73183).shuffle(block)
        for t, lang in block:
            yield model, t, lang


def setup():
    meta, _ = study.prior.read_archive(study.BASELINE)
    files = [Path(__file__).resolve(), study.HERE / "agent_fresh_tasks.py", study.HERE / "agent-fresh-protocol.md"]
    return {**study.manifest(), "study": "fresh-agent-expression-v1", "model_digests": meta["model_digests"],
            "fresh_task_sha256": study.prior.fingerprint(json.dumps(TASKS, sort_keys=True).encode()),
            "fresh_sources": {str(f.relative_to(study.ROOT)): study.prior.fingerprint(f.read_bytes()) for f in files}}


def preflight(tools):
    for task in TASKS:
        for lang in study.catalog.base.LANGUAGES:
            ref = study.source_for(task, lang, "reference")
            status, detail = study.evaluate(tools, lang, ref, task["public"] + task["heldout"])
            if status != "pass":
                raise ValueError(f"{task['id']}/{lang}: reference check failed, {detail}")
            status, _ = study.evaluate(tools, lang, study.source_for(task, lang), task["public"])
            if status != "wrong_answer":
                raise ValueError("Expected at least one semantic public failure in the starter.")


def run(path, replay, port):
    tools = study.catalog.base.prior.Tools(study.ROOT, study.GPP)
    tools.canaries()
    config = setup()
    if replay:
        archived, rows = study.prior.read_archive(path)
        if any(archived.get(k) != v for k, v in config.items()):
            raise ValueError("Study source or corpus changed.")
        for (model, task, lang), r in zip(roster(), rows, strict=True):
            study.trial(tools, model, task, lang, None, archived, r)
        print(f"Replayed {len(rows)} new-task trials.")
    else:
        print("Checking starters and reference implementations.", flush=True)
        preflight(tools)
        print("Reference programs passed 135 evaluations; every starter fails a public example.", flush=True)
        info = study.prior.live_metadata(port, config)
        meta = {**config, "ollama": info["ollama"], "gpp_sha256": study.prior.fingerprint(study.GPP.read_bytes())}
        with path.open("x", buffering=1) as store:
            print(json.dumps(meta), file=store)
            for model, task, lang in roster():
                row = study.trial(tools, model, task, lang, port, meta)
                print(json.dumps(row), file=store)
                print(model, task["id"], lang, row["outcome"], flush=True)


def report(path):
    _, rows = study.prior.read_archive(path)
    keys = [(r["model"], r["task"], r["language"]) for r in rows]
    if keys != [(m, t["id"], lang) for m, t, lang in roster()]:
        raise ValueError("Incomplete or reordered new-task roster.")
    print("# Native expression repairs on three new scalar contracts\n")
    print("Each contract has two callers, three visible tests and twelve withheld checks. Two models "
          "ran all three contracts in each language. All failed calls are included.\n")
    print("| Model | Language | First accepted | Final accepted | Retries | Input tokens | Output tokens | Tokens/accept | Workflow seconds | Model seconds |")
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for m in study.catalog.base.prior.MODELS:
        for lang in study.catalog.base.LANGUAGES:
            g = [r for r in rows if r["model"] == m and r["language"] == lang]
            calls = [a for r in g for a in r["attempts"]]
            first = sum(r["outcome"] == "accepted" and len(r["attempts"]) == 1 for r in g)
            count = sum(r["outcome"] == "accepted" for r in g)
            inputs = sum(a["reply"]["prompt_eval_count"] for a in calls)
            outputs = sum(a["reply"]["eval_count"] for a in calls)
            cost = f"{(inputs + outputs) / count:,.1f}" if count else "undefined"
            print(f"| {m} | {lang} | {first}/3 | {count}/3 | {len(calls)-3} | {inputs:,} | {outputs:,} | "
                  f"{cost} | {sum(r['wall_ms'] for r in g)/1000:.2f} | {sum(a['model_ms'] for a in calls)/1000:.2f} |")
    print("\n| Model | Task | Language | First public check | Final result |")
    print("|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['model']} | {r['task']} | {r['language']} | {r['attempts'][0]['status']} | {r['outcome']} |")
    print("\nThese three locally authored tasks cover scalar arithmetic and interval handling. The block "
          "was frozen before inference on these tasks. It does not measure general software development, "
          "and a cost per accepted edit is undefined for groups with no accepted change.")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    modes = cli.add_mutually_exclusive_group()
    modes.add_argument("--replay", action="store_true")
    modes.add_argument("--report", action="store_true")
    cli.add_argument("--port", type=int, default=11434)
    cli.add_argument("archive", type=Path)
    args = cli.parse_args()
    if args.report:
        report(args.archive)
    else:
        with TemporaryDirectory(prefix="gpp-agent-frozen-") as directory:
            frozen = Path(directory) / "gpp"
            shutil.copy2(study.GPP, frozen)
            study.GPP = frozen
            run(args.archive, args.replay, args.port)
