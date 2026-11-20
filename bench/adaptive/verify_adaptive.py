"""Verify an archived adaptive benchmark without contacting a model server.

--replay uses the frozen study Python environment, native tools and sandbox.
--tokenizer independently checks FIM input usage with the pinned local tokenizer.
Visible completions omit stop tokens; output totals use the server's usage.
"""
import argparse
import ast
from collections import Counter
from datetime import datetime
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import platform
import plistlib
import random
import re
import subprocess
import sys
from textwrap import dedent


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# The same model, template, toolchain, tokenizer and stop settings were pinned
# independently in v5. The v6 roster and task digests below were taken before
# the first inference completed, from the on-disk source and corpus.
audit = load_file("v5_audit", HERE.parent / "maintenance/verify.py")
require = audit.require
FILES = "ec340c240e7d0f8bd07a436b02364851f38ba0e98dbd3c595d94b22924ffc1b1"
CORPUS = "d5d42676206e80b51642c964ec825f375f34762712200c943072376f10dc20c5"
ARMS = ("gpp_adaptive", "python_adaptive", "rust_adaptive", "gpp_target", "gpp_context")
VERSIONS = {"python": "3.11.0", "rust": "rustc 1.97.1 (8bab26f4f 2026-07-14) (Homebrew)",
            "mypy": "mypy 1.15.0 (compiled: yes)", "ollama_version": "0.6.2",
            "host": "macOS-26.5.2-arm64-arm-64bit"}


def check_fingerprints(meta):
    require(meta["type"] == "metadata" and meta["study"] == "multi-caller-adaptive-v6", "wrong study")
    require(audit.json_digest(meta["file_sha256"]) == FILES, "frozen source roster or fingerprint changed")
    for rel, digest in meta["file_sha256"].items():
        require(audit.digest(ROOT / rel) == digest, f"modified dependency: {rel}")
    require(audit.digest(audit.GPP) == meta["gpp_sha256"] == audit.COMPILER, "compiler binary differs")
    require(meta["model_digests"] == {audit.MODEL: audit.MODEL_DIGEST}, "unexpected model digest")
    require(sha256(meta["model_template"].encode()).hexdigest() == audit.TEMPLATE, "model template differs")
    require(all(meta[k] == v for k, v in VERSIONS.items()), "archived software/host versions differ")


def check_installed(tools, meta):
    require(platform.platform() == meta["host"] and platform.python_version() == meta["python"],
            "replay host or Python version differs")
    for k, args in [("rust", [tools.rustc, "--version"]), ("mypy", [tools.python, "-m", "mypy", "--version"])]:
        require(subprocess.check_output(args, text=True).strip() == meta[k], f"replay {k} differs")
    root = Path(os.environ.get("OLLAMA_MODELS", Path.home() / ".ollama/models"))
    model = root / "manifests/registry.ollama.ai/library/qwen2.5-coder/7b"
    require(audit.digest(model) == audit.MODEL_DIGEST, "installed model manifest differs")
    manifest = json.loads(model.read_bytes())
    for blob in [manifest["config"], *manifest["layers"]]:
        sha = sha256()
        with (root / "blobs" / blob["digest"].replace(":", "-")).open("rb") as stream:
            while chunk := stream.read(8 * 1024 * 1024):
                sha.update(chunk)
        require("sha256:" + sha.hexdigest() == blob["digest"], "installed Ollama blob differs")
    info = plistlib.loads(Path("/Applications/Ollama.app/Contents/Info.plist").read_bytes())
    require(info["CFBundleShortVersionString"] == meta["ollama_version"], "installed Ollama version differs")


def check_manifest(meta, tasks):
    require(len(tasks) == len({t["id"] for t in tasks}) == 8, "unexpected task count")
    require(meta["tasks"] == [t["id"] for t in tasks] and meta["corpus_sha256"] == audit.json_digest(tasks) == CORPUS,
            "task content or order differs")
    require(meta["targets"] == {t["id"]: t["target"] for t in tasks}, "target mapping differs")
    require(meta["sources"] == {t["id"]: {k: t[k] for k in ("source_url", "provenance")} for t in tasks},
            "provenance differs")
    counts = tuple(sum(len(t[k]) for t in tasks) for k in ("public", "heldout"))
    require(counts == (meta["public_cases"], meta["hidden_cases"]) == (31, 124)
            and meta["reference_cases_checked"] == sum(counts) * 3, "oracle or reference counts differ")
    require(meta["conditions"] == list(ARMS) and meta["seeds"] == [42] and meta["models"] == [audit.MODEL]
            and meta["primary_comparator"] == "python_adaptive" and meta["order_seed"] == 12713, "allocation differs")
    require(meta["default_stops"] == [] and meta["boundary_stops"] == audit.STOPS
            and meta["model_options"] == audit.OPTIONS
            and meta["retry_options"] == dict(audit.OPTIONS, temperature=0.25, seed=43), "sampling differs")
    require(datetime.fromisoformat(meta["started_at"]).tzinfo is not None, "missing zoned study timestamp")
    rng = random.Random(12713)
    shuffled = tasks.copy()
    rng.shuffle(shuffled)
    assignments = []
    for task in shuffled:
        arms = list(ARMS)
        rng.shuffle(arms)
        assignments.extend((audit.MODEL, 42, task["id"], arm) for arm in arms)
    return assignments


def check_public_reachability(study, task, lang, base):
    from fragments import _brace_tokens
    declarations = study.maintenance.functions(base, lang)
    edges = {}
    for fn in declarations.values():
        if lang == "python":
            names = {n.func.id for n in ast.walk(ast.parse(dedent(fn.body)))
                     if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
        else:
            tokens = [t for t, _, _ in _brace_tokens(fn.body)]
            names = {t for i, t in enumerate(tokens[:-1]) if tokens[i + 1] == "("
                     and (not i or tokens[i - 1] not in (".", ":", "fn"))}
        edges[fn.name] = names & declarations.keys()
    target = task["target"]
    reaches_target = {target}
    while new := {caller for caller, callees in edges.items() if callees & reaches_target} - reaches_target:
        reaches_target.update(new)
    for entry, _, _ in task["public"]:
        require(entry in reaches_target, f"{task['id']} {lang}: public entry {entry} cannot reach {target}")


def check_call(study, task, row, attempt, i, prior, base):
    arm, lang = row["condition"], row["language"]
    previous = prior["response"] if prior else None
    feedback = prior["public_detail"] if prior else None
    failed = prior["public_failed_entry"] if prior else None
    show = arm == "gpp_context" or (arm.endswith("_adaptive") and failed is not None and failed != task["target"])
    require(attempt["caller_context"] is show, "caller policy differs")
    require(study.render(task, lang, base, show, previous, feedback)
            == (attempt["prompt"], attempt["suffix"], lang), "prompt or literal suffix differs")
    # Inspect the fixed prompt section separately from the untrusted previous completion.
    initial_sections = attempt["prompt"].split("Previous attempt:", 1)[0]
    require(("Read-only caller excerpts:" in initial_sections) == show, "actual caller excerpts differ from policy")
    sampling = dict(audit.OPTIONS, stop=audit.STOPS[lang])
    if i:
        sampling.update(seed=43, temperature=0.25)
    require(attempt["sampling"] == sampling, "per-call options differ")
    require(isinstance(attempt["response"], str) and isinstance(attempt["public_detail"], str), "missing text")
    for key, lo, hi in [("input_tokens", 1, 2048), ("output_tokens", 0, 240)]:
        value = attempt[key]
        require(type(value) is int and lo <= value <= hi, f"invalid {key}")
    require(attempt["output_tokens"] or not attempt["response"], "text reported with zero output tokens")
    require(attempt["done_reason"] in ("length", "stop")
            and (attempt["done_reason"] != "length" or attempt["output_tokens"] == 240), "invalid termination")
    require(all(audit.finite_ms(attempt[k]) for k in ("model_ms", "load_ms", "tool_ms", "generation_ms")),
            "invalid duration")
    status, entry = attempt["public_outcome"], attempt["public_failed_entry"]
    require(status in {"pass", *audit.ERRORS} and ((status == "pass") == (attempt["public_detail"] == "")),
            "invalid public result")
    if attempt["stage"] == "patch":
        require(entry is None and status == "check_error" and attempt["patch_sha256"] is None, "invalid patch failure")
    else:
        require(attempt["stage"] == "public" and re.fullmatch("[0-9a-f]{64}", attempt["patch_sha256"] or ""),
                "invalid patch digest")
    if entry is not None:
        require(status in ("wrong_answer", "runtime_error") and entry in {name for name, _, _ in task["public"]},
                "unattributable failure entry")
    for name, args, _ in task["public"]:
        call = f"{name}({study.arguments(args, lang)})"
        if attempt["public_detail"].startswith((call + " returned ", call + " failed during execution.")):
            require(entry == name, "diagnostic and attributed entry disagree")


def check_trial(study, task, row, base):
    arm = row["condition"]
    require((row["language"], row["kind"], row["form"], row["target"])
            == (arm.split("_")[0], "maintenance", task["form"], task["target"]), "trial labels differ")
    calls = row["attempts"]
    require(1 <= len(calls) <= 2, "invalid attempt count")
    for i, a in enumerate(calls):
        check_call(study, task, row, a, i, calls[i - 1] if i else None, base)
        if a["public_outcome"] == "pass":
            require(i == len(calls) - 1 and a["outcome"] in {"accepted", *("heldout_" + k for k in audit.ERRORS)},
                    "public success must end attempts and lead to a hidden result")
        else:
            require(a["outcome"] == a["public_outcome"], "wrong terminal failure category")
    passed = calls[-1]["public_outcome"] == "pass"
    accepted = calls[-1]["outcome"] == "accepted"
    require((row["accepted"] is accepted and row["first_accepted"] is (accepted and len(calls) == 1)),
            "trial acceptance flags differ")
    require(audit.finite_ms(row["wall_ms"]) and row["wall_ms"] + 0.01 >= sum(a["model_ms"] + a["tool_ms"] for a in calls),
            "attempt durations exceed workflow time")
    require(audit.finite_ms(row["heldout_ms"]) and isinstance(row["heldout_detail"], str), "invalid held-out timing")
    if passed:
        require(row["heldout_ms"] > 0 and bool(row["heldout_detail"]) != accepted, "missing hidden evaluation")
    else:
        require(len(calls) == 2 and not row["heldout_ms"] and not row["heldout_detail"], "repair or holdout gate differs")


def replay(study, tools, row, task, base):
    lang = row["language"]
    target = study.maintenance.functions(base, lang)[task["target"]]
    accepted = False
    for a in row["attempts"]:
        status, detail, patched = study.materialize(tools, task, lang, lang, base, a["response"])
        stage, entry = ("public" if status == "pass" else "patch"), None
        require(stage == a["stage"] and (sha256(patched.encode()).hexdigest() if patched else None) == a["patch_sha256"],
                "replayed patch stage or fingerprint differs")
        if status == "pass":
            require(patched.startswith(base[:target.start]) and patched.endswith(base[target.end:]),
                    "non-target source changed")
            require(study.maintenance.functions(patched, lang)[target.name].signature == target.signature,
                    "target signature changed")
            status, detail, entry = study.public_evaluate(tools, lang, patched, task["public"])
        require((status, detail, entry) == (a["public_outcome"], a["public_detail"], a["public_failed_entry"]),
                f"replayed public result/diagnostic/entry differs: {(status, detail, entry)!r}")
        if status == "pass":
            hidden, detail = study.evaluate(tools, lang, patched, task["heldout"], already_checked=True)
            accepted = hidden == "pass"
            require(("accepted" if accepted else "heldout_" + hidden, detail) == (a["outcome"], row["heldout_detail"]),
                    f"replayed hidden verdict/diagnostic differs: {(hidden, detail)!r}")
    require(accepted is row["accepted"], "replayed acceptance differs")


def verify(log, do_replay, report_file, tokenizer):
    data = log.read_bytes()
    meta, *rows = map(json.loads, data.splitlines())
    check_fingerprints(meta)
    import run_adaptive as study
    groups = [load_file("adaptive_verify_" + key, HERE / f"cases_{key}.py").TASKS for key in ("a", "b")]
    tasks = [*groups[0], *groups[1]]
    observed = [(r["model"], r["seed"], r["task"], r["condition"]) for r in rows]
    require(observed == check_manifest(meta, tasks), "incomplete, duplicate, unknown or reordered assignment")
    fixtures = {t["id"]: t for t in tasks}
    bases = {}
    for task in tasks:
        for lang in ("gpp", "python", "rust"):
            base = study.source_for(task, lang)
            check_public_reachability(study, task, lang, base)
            bases[task["id"], lang] = base
    tools = None
    if do_replay:
        tools = study.Tools(ROOT, audit.GPP)
        check_installed(tools, meta)
        tools.canaries()
    totals = {arm: Counter() for arm in ARMS}
    for row in rows:
        task, arm = fixtures[row["task"]], row["condition"]
        try:
            base = bases[task["id"], row["language"]]
            check_trial(study, task, row, base)
            if do_replay:
                replay(study, tools, row, task, base)
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError(f"{task['id']}/{arm}: {exc}") from exc
        calls = row["attempts"]
        count = totals[arm]
        count["assigned"] += 1
        count["accepted"] += calls[-1]["outcome"] == "accepted"
        count["attempts"] += len(calls)
        count["input"] += sum(a["input_tokens"] for a in calls)
        count["output"] += sum(a["output_tokens"] for a in calls)
        count["hidden"] += calls[-1]["public_outcome"] == "pass"
        count["retry_context"] += len(calls) == 2 and calls[1]["caller_context"]
    from report_adaptive import read_log, totals as reported_totals
    _, _, report_records = read_log(log)
    for arm, c in totals.items():
        require((c["assigned"], c["accepted"], c["input"] + c["output"]) == reported_totals(report_records, arm),
                f"report totals differ for {arm}")
        print(f"{arm}: {c['accepted']}/{c['assigned']} accepted; {c['attempts']} calls; "
              f"{c['input']} input + {c['output']} output = {c['input'] + c['output']} tokens; "
              f"{c['retry_context']} retries with excerpts")
    if tokenizer:
        audit.retokenize(tokenizer, [a for r in rows for a in r["attempts"]])
    if report_file:
        rendered = subprocess.check_output([sys.executable, "-B", HERE / "report_adaptive.py", log])
        require(rendered == report_file.read_bytes(), "archived report differs from a fresh rendering")
    require(data == log.read_bytes(), "log changed during verification")
    counts = sum(totals.values(), Counter())
    print(f"Verified {counts['assigned']} assignments, {counts['attempts']} calls, {counts['accepted']} accepted. "
          f"Log SHA-256 {sha256(data).hexdigest()}")
    if do_replay:
        print(f"Replayed every completion, public outcome, failure attribution and all {counts['hidden']} triggered hidden evaluations.")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("log", type=Path)
    cli.add_argument("--report", type=Path, help="compare saved Markdown to a freshly rendered report")
    cli.add_argument("--replay", action="store_true", help="run all generated code only in the frozen sandbox")
    cli.add_argument("--tokenizer", type=Path, help="independently retokenize all prompts with pinned local Qwen tokenizer.json")
    args = cli.parse_args()
    try:
        verify(args.log, args.replay, args.report, args.tokenizer)
    except (ValueError, KeyError, TypeError, ImportError, OSError, subprocess.CalledProcessError) as exc:
        cli.exit(1, f"{exc}\n")
