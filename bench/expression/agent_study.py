"""Run, replay or report matched native expression generation with public feedback."""

import argparse
from contextlib import nullcontext
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
import time

import catalog_study as catalog
import repair_study as prior
from agent_edit import attempts, diagnostic
from caller_context import caller_context
from evaluate import arguments
from evaluate_project import ENTRY, MODULE, evaluate, functions, source_for
from indexed_edit import order_spans
from propose import ollama
from test_propose import mock_ollama


HERE, ROOT, GPP = prior.HERE, prior.ROOT, prior.GPP
CLI = ROOT / "tools/agent_edit.py"
BASELINE = HERE / "results/catalog.jsonl"


def elapsed(start):
    return round((time.monotonic() - start) * 1000)


def manifest():
    files = [CLI, HERE / "agent-protocol.md", Path(__file__).resolve(), HERE / "sites.py",
             HERE / "tasks.py", ROOT / "tools/indexed_edit.py", ROOT / "tools/propose.py",
             ROOT / "tools/caller_context.py", HERE.parent / "adaptive/run_adaptive.py",
             HERE.parent / "empirical/evaluate.py", HERE.parent / "maintenance/evaluate_project.py"]
    return {"study": "matched-agent-expression-v1", "baseline_sha256": prior.fingerprint(BASELINE.read_bytes()),
            "sources": {str(p.relative_to(ROOT)): prior.fingerprint(p.read_bytes()) for p in files},
            "task_sha256": prior.fingerprint(json.dumps(prior.TASKS, sort_keys=True).encode()),
            "rust_parser_sha256": prior.fingerprint(catalog.base.RUST_PARSER.read_bytes())}


def gpp(tools, task, model, port, meta, saved):
    with TemporaryDirectory(prefix="gpp-agent-study-") as directory:
        work = Path(directory)
        file, cases, fragment = work / "base.gpp", work / "public.json", work / "change.expr"
        original = MODULE + source_for(task, "gpp") + ENTRY
        file.write_text(original)
        cases.write_text(json.dumps([dict(function=n, args=a, expected=v) for n, a, v in task["public"]]))
        if saved:
            context = mock_ollama([a["reply"]["response"] for a in saved["attempts"]],
                                  model_name=model, digest=meta["model_digests"][model])
        else:
            context = nullcontext((port, []))
        with context as (connection, exchanges):
            result = json.loads(subprocess.check_output(
                [sys.executable, "-B", CLI, file, "--function", task["target"], "--task", task["description"],
                 "--model", model, "--cases", cases, "--gpp", GPP, "--port", str(connection),
                 "--transcript", "-o", fragment], text=True, timeout=420,
            ))
        logs = result["attempts"]
        if saved:
            requests = [body for path, body in exchanges if path == "/api/generate"]
            if requests != [a["request"] for a in saved["attempts"]]:
                raise ValueError("Product sent a different request.")
        if file.read_text() != original or (result["status"] == "proposed") != fragment.exists():
            raise ValueError("Product publication status differed from disk.")
        patch = None
        if fragment.exists():
            apply = result["apply"]
            if apply[0:5] != [str(GPP), "edit", str(file), "--function", task["target"]]:
                raise ValueError("Unexpected apply command.")
            if fragment.read_text() != logs[-1]["replacement"].strip() + "\n":
                raise ValueError("Published fragment differs from the response.")
            complete = subprocess.check_output([*apply, "--stdout"], text=True, timeout=15)
            if (prior.fingerprint(complete.encode()) != logs[-1]["patch_sha256"]
                    or not complete.startswith(MODULE) or not complete.endswith(ENTRY)):
                raise ValueError("Checked preview changed.")
            patch = complete[len(MODULE):-len(ENTRY)]
        return logs, patch


def initial_examples(tools, task, language, source):
    examples = []
    for name, args, expected in task["public"]:
        status, detail = evaluate(tools, language, source, [(name, args, expected)], already_checked=True)
        call = f"{name}({arguments(args, language)})"
        if status == "pass":
            actual = str(expected)
        elif status == "wrong_answer":
            match = re.fullmatch(re.escape(call) + r" returned (-?\d+)\. Expected (-?\d+)\.", detail)
            if not match or int(match[2]) != expected:
                raise ValueError(detail)
            actual = match[1]
        else:
            raise ValueError(f"Unexpected starter failure: {detail}")
        examples.append(f"{call} returned {actual}; expected {expected}.")
    return examples


def comparator(tools, task, model, lang, port, saved):
    source = source_for(task, lang)
    target = catalog.base.sites.function_text(task, lang, source)
    spans = order_spans(catalog.base.sites.catalog(tools, catalog.base.RUST_PARSER, task, lang, source))
    examples = initial_examples(tools, task, lang, source)
    callers = caller_context([f.record() for f in functions(source, lang).values()], task["target"], lang)
    answers = iter(saved["attempts"]) if saved else None

    def generate(req):
        if answers is None:
            return ollama(port, "generate", req)
        recorded = next(answers)
        if req != recorded["request"]:
            raise ValueError(f"Different {lang} inference payload.")
        return dict(recorded["reply"], done=True)

    def validate(span, replacement):
        status, detail, patch = catalog.base.sites.apply(tools, catalog.base.RUST_PARSER, task, lang,
                                                        source, span, replacement)
        if status != "pass":
            return status, detail, None
        status, detail, _ = catalog.base.prior.previous.public_evaluate(tools, lang, patch, task["public"])
        return status, detail, patch.encode()

    logs, patch = attempts(model, lang, task["description"], examples, target, spans, callers, generate, validate)
    return logs, patch.decode() if patch is not None else None


def trial(tools, model, task, lang, port, meta, saved=None):
    start = time.monotonic()
    if lang == "gpp":
        logs, patch = gpp(tools, task, model, port, meta, saved)
    else:
        logs, patch = comparator(tools, task, model, lang, port, saved)
    wall = elapsed(start)
    hidden_start = time.monotonic()
    status, detail = logs[-1]["status"], logs[-1]["detail"]
    if patch is not None:
        public, msg = evaluate(tools, lang, patch, task["public"], already_checked=True)
        if public != "pass":
            raise ValueError(f"Independent public score differs from the editor: {msg}")
        hidden, detail = evaluate(tools, lang, patch, task["heldout"], already_checked=True)
        status = "accepted" if hidden == "pass" else "withheld_" + hidden
    row = dict(model=model, language=lang, task=task["id"], attempts=logs, wall_ms=wall,
               scorer_ms=elapsed(hidden_start), outcome=status, detail=diagnostic(detail))
    if saved:
        if len(logs) != len(saved["attempts"]):
            raise ValueError("Unexpected retry count.")
        for record, reference in zip(logs, saved["attempts"]):
            if record["reply"]["response"] != reference["reply"]["response"]:
                raise ValueError("Completion changed.")
            record.update(reply=reference["reply"], model_ms=reference["model_ms"],
                          validation_ms=reference["validation_ms"])
        row.update(wall_ms=saved["wall_ms"], scorer_ms=saved["scorer_ms"])
        if row != saved:
            raise ValueError(f"Replay mismatch for {model}/{lang}/{task['id']}.")
    return row


def run(path, replay, port):
    config = manifest()
    base_meta, baseline = prior.read_archive(BASELINE)
    if replay:
        meta, rows = prior.read_archive(path)
        if any(meta[k] != value for k, value in config.items()):
            raise ValueError("Study source or fixture changed.")
    else:
        info = prior.live_metadata(port, base_meta)
        meta = {**config, "ollama": info["ollama"], "model_digests": base_meta["model_digests"],
                "gpp_sha256": prior.fingerprint(GPP.read_bytes()), "platform": platform.platform(),
                "python": platform.python_version(), "rustc": subprocess.check_output(["rustc", "-V"], text=True).strip(),
                "mypy": subprocess.check_output([sys.executable, "-m", "mypy", "--version"], text=True).strip()}
        rows = []
    tools = catalog.base.prior.Tools(ROOT, GPP)
    tools.canaries()
    tasks = {task["id"]: task for task in prior.TASKS}
    if replay:
        if [(r["model"], r["language"], r["task"]) for r in rows] != [
            (b["model"], b["language"], b["task"]) for b in baseline
        ]:
            raise ValueError("Recorded roster is incomplete or reordered.")
        for r in rows:
            trial(tools, r["model"], tasks[r["task"]], r["language"], None, meta, r)
        print(f"Replayed {len(rows)} assignments through checked adapters, including the GPT++ CLI.")
    else:
        with path.open("x", buffering=1) as store:
            print(json.dumps(meta), file=store)
            for b in baseline:
                r = trial(tools, b["model"], tasks[b["task"]], b["language"], port, meta)
                print(json.dumps(r), file=store)
                print(r["model"], r["task"], r["language"], r["outcome"], flush=True)


def report(path):
    _, rows = prior.read_archive(path)
    _, baseline = prior.read_archive(BASELINE)
    keys = ("model", "task", "language")
    if [[r[k] for k in keys] for r in rows] != [[r[k] for k in keys] for r in baseline]:
        raise ValueError("Incomplete matched roster.")
    print("# Generating checked expressions with public feedback\n")
    print("Three development tasks for each model and language. Accepted changes passed public and "
          "withheld checks. Every model call counts toward usage.\n")
    print("| Model | Language | First accepted | Final accepted | Retries | Input tokens | Output tokens | Tokens/accept | Workflow seconds | Model seconds |")
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for model, lang in dict.fromkeys((r["model"], r["language"]) for r in rows):
        group = [r for r in rows if (r["model"], r["language"]) == (model, lang)]
        calls = [a for r in group for a in r["attempts"]]
        inputs = sum(a["reply"]["prompt_eval_count"] for a in calls)
        outputs = sum(a["reply"]["eval_count"] for a in calls)
        first = sum(r["outcome"] == "accepted" and len(r["attempts"]) == 1 for r in group)
        solved = sum(r["outcome"] == "accepted" for r in group)
        cost = f"{(inputs + outputs) / solved:,.1f}" if solved else "undefined"
        print(f"| {model} | {lang} | {first}/{len(group)} | {solved}/{len(group)} | {len(calls)-len(group)} | "
              f"{inputs:,} | {outputs:,} | {cost} | {sum(r['wall_ms'] for r in group)/1000:.2f} | "
              f"{sum(a['model_ms'] for a in calls)/1000:.2f} |")
    print("\n| Task | Model | Language | First public check | Final result |")
    print("|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['task']} | {r['model']} | {r['language']} | {r['attempts'][0]['status']} | {r['outcome']} |")
    print("\nThe earlier one-shot catalog accepted zero changes in all six model/language groups. This "
          "follow-up changes caller context, public observations, syntax guidance and retry policy together. "
          "The same three previously inspected extracts appear in both studies. Timing includes model loading "
          "and local validation and depends on toolchain, cache and host. These observations do not establish "
          "a general advantage for any language.")


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
        run(args.archive, args.replay, args.port)
