"""Run, replay or report six contract-guided local model repair assignments."""

import argparse
from contextlib import nullcontext
import json
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
import time

import study
from fixtures import TASKS

sys.path.insert(0, str(study.ROOT / "tools"))
from propose import ollama
from test_propose import mock_ollama


MODELS = {
    "qwen2.5-coder:7b": "dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364",
    "starcoder2:3b": "f67ae0f64584a4d1d7c609bf4778dd0d07054582362d21ca4f0eddea22aafd0c",
}


def manifest(gpp):
    local = ["bench/contracts/model-protocol.md", "bench/contracts/model_study.py", "bench/contracts/study.py",
             "bench/contracts/fixtures.py", "tools/agent_edit.py", "tools/propose.py", "tools/indexed_edit.py",
             "tools/caller_context.py", "tools/contract_check.py", "tools/contract_repair.py",
             "tools/distinguish.py", "tools/repair.py", "tools/probe.py"]
    local.extend(str(p.relative_to(study.ROOT)) for p in sorted((study.ROOT / "src").glob("*.rs")))
    return {"study": "model-finite-contract-v1", "model_digests": MODELS,
            "sources": {p: study.sha((study.ROOT / p).read_bytes()) for p in local},
            "gpp_sha256": study.sha(gpp.read_bytes())}


def trial(task, model, gpp, cli, *, port, saved=None):
    original = task.module()
    with TemporaryDirectory(prefix="gpp-model-contract-case-") as tmp:
        work = Path(tmp)
        file, fragment = work / "starter.gpp", work / "selected.expr"
        file.write_text(original)
        if saved is None:
            context = nullcontext((port, []))
        else:
            replies = [a["reply"]["response"] for a in saved["product"]["attempts"]]
            context = mock_ollama(replies, model_name=model, digest=MODELS[model])
        request = f"Repair {task.target} to satisfy the declared contracts."
        with context as (connection, observed):
            args = [sys.executable, "-B", cli, file, "--function", task.target, "--model", model,
                    "--task", request, "--contracts", "--transcript", "--port", connection, "--gpp", gpp, "-o", fragment]
            start = time.monotonic()
            proc = study.run(args, timeout=420)
            wall_ms = round((time.monotonic() - start) * 1000)
        data = json.loads(proc.stdout)
        checks = data["attempts"]
        study.require(len(checks) in (1, 2), "Expected one attempt plus at most one retry")
        study.require(file.read_text() == original, "Product changed the original")
        study.require(data["revision"] == "sha256:" + study.sha(original.encode()), "Wrong original revision")
        study.require(fragment.exists() == (data["status"] == "proposed"), "Incorrect publication status")
        score = None
        if fragment.exists():
            application = data["apply"]
            study.require(application[:5] == [str(gpp), "edit", str(file), "--function", task.target],
                          "Invalid generated apply command")
            study.require(application[7:] == ["--expr", str(fragment), "--expect", data["revision"],
                                              "--verify", "--budget", "10000"], "Missing checked apply guard")
            patched = study.run([*application, "--stdout"]).stdout
            study.require(fragment.read_text().strip() == checks[-1]["replacement"].strip(),
                          "Published a different expression")
            digest = study.sha(patched.encode())
            study.require(digest == checks[-1]["patch_sha256"], "Saved expression produced a different patch")
            preview = work / "preview.gpp"
            preview.write_text(patched)
            verified = study.verify(gpp, preview, len(task.tuples()))
            values = study.direct(gpp, task, preview)
            judgement = study.independent(task, values)
            study.assert_diagnostic(task, values, judgement, verified)
            study.require(judgement["domain_pass"], "A published expression failed the independent domain scorer")
            score = {"patched_sha256": digest, "verified": verified, "observed": values, "independent": judgement}
        if saved is not None:
            requests = [body for path, body in observed if path == "/api/generate"]
            archived = saved["product"]["attempts"]
            study.require(requests == [a["request"] for a in archived], "Replay sent different prompts")
            for a, old in zip(checks, archived, strict=True):
                study.require(a["reply"]["response"] == old["reply"]["response"], "Reply text changed")
                a["reply"] = old["reply"]
                a["model_ms"] = old["model_ms"]
                a["validation_ms"] = old["validation_ms"]
            wall_ms = saved["cli_ms"]
        else:
            for a in checks:
                study.require(all(type(a["reply"].get(k)) is int for k in ("prompt_eval_count", "eval_count")),
                              "Ollama did not report token usage")
        result = {"model": model, "task": task.target, "task_request": request,
                  "product": study.normalized(data, work, gpp), "score": score, "cli_ms": wall_ms}
        if saved is not None:
            study.require(study.same_json(saved, result), f"Replayed product data differs for {model}/{task.target}")
        return result


def run(path, gpp, port, replay):
    with TemporaryDirectory(prefix="gpp-contract-pinned-") as scratch:
        frozen = Path(scratch)
        binary = frozen / "gpp"
        shutil.copy2(gpp, binary)
        shutil.copytree(study.ROOT / "tools", frozen / "tools", ignore=shutil.ignore_patterns("__pycache__"))
        cli = frozen / "tools/agent_edit.py"
        meta = manifest(binary)
        for name, expected in meta["sources"].items():
            if name.startswith("tools/"):
                study.require(study.sha((frozen / name).read_bytes()) == expected, "Source changed during snapshot")
        order = [(m, t) for m in MODELS for t in TASKS]
        if replay:
            archived, rows = study.read(path)
            study.require(archived["sources"] == meta["sources"] and archived["model_digests"] == MODELS,
                          "Product, study or model digests changed")
            for (model, task), record in zip(order, rows, strict=True):
                trial(task, model, binary, cli, port=None, saved=record)
            print(f"Replayed {len(rows)} contract-guided model trials and every generated request.")
        else:
            models = {m["name"]: m["digest"] for m in ollama(port, "tags")["models"]}
            study.require(all(models[m] == v for m, v in MODELS.items()), "A local model differs from the pinned digest")
            meta["ollama"] = ollama(port, "version")["version"]
            with path.open("x", buffering=1) as store:
                print(json.dumps(meta), file=store)
                for model, task in order:
                    record = trial(task, model, binary, cli, port=port)
                    print(json.dumps(record), file=store)
                    print(model, task.target, record["product"]["status"], flush=True)


def report(path):
    meta, rows = study.read(path)
    study.require([(r["model"], r["task"]) for r in rows] == [(m,t.target) for m in MODELS for t in TASKS],
                  "Incomplete assignment roster")
    print("# Local models repairing finite contracts\n")
    print("Each model received the three original modules and their declared contracts. The compiler listed "
          "available edit sites, checked the generated replacement and allowed at most one diagnostic retry. "
          "Independent direct evaluation checked each selected expression over the complete declared domain.\n")
    print("| Model | First accepted | Final accepted | Calls | Input tokens | Output tokens | Tokens/accept | CLI seconds |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|")
    for model in MODELS:
        group = [r for r in rows if r["model"] == model]
        calls = [a for r in group for a in r["product"]["attempts"]]
        accepted = sum(bool(r["score"]) for r in group)
        first = sum(bool(r["score"]) and len(r["product"]["attempts"]) == 1 for r in group)
        inputs = sum(a["reply"]["prompt_eval_count"] for a in calls)
        outputs = sum(a["reply"]["eval_count"] for a in calls)
        cost = f"{(inputs + outputs) / accepted:,.1f}" if accepted else "undefined"
        print(f"| {model} | {first}/3 | {accepted}/3 | {len(calls)} | {inputs:,} | {outputs:,} | {cost} | "
              f"{sum(r['cli_ms'] for r in group)/1000:.2f} |")
    print("\n| Model | Task | First validation | Final validation | Accepted edit | Extra inputs passing |")
    print("|---|---|---|---|---|---:|")
    for r in rows:
        calls, score = r["product"]["attempts"], r["score"]
        expr = "`" + calls[-1]["replacement"].strip().replace("|", r"\|") + "`" if score else "—"
        extra = f"{score['independent']['extra_correct']}/{score['independent']['extra_total']}" if score else "—"
        print(f"| {r['model']} | {r['task']} | {calls[0]['status']} | {calls[-1]['status']} | {expr} | {extra} |")
    if "collection_note" in meta:
        print("\nA harness assertion interrupted the original Qwen/capacity collection before it archived "
              "that assignment. The completed Qwen/carry record was retained. The affected assignment was "
              "recollected under the same protocol. The table covers the six archived trials. Usage for "
              "the interrupted assignment is unavailable.")
    print("\nAll failed calls in the six archived trials contribute to the token totals. The five extra inputs per task were scorer-only "
          "checks outside the contracts. A finite certificate covers the declared tuples. This small "
          "development run has no matched model comparison against Python, Rust or unassisted generation.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--replay", action="store_true")
    mode.add_argument("--report", action="store_true")
    parser.add_argument("--gpp", type=Path, default=study.ROOT / "target/debug/gpp")
    parser.add_argument("--port", type=int, default=11434)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    if args.report:
        report(args.archive)
    else:
        run(args.archive, args.gpp, args.port, args.replay)
