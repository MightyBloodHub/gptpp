"""Offline v7 archive audit. --replay rescores all completions in the study sandbox.

Optional --qwen-tokenizer and --star-tokenizer take independently downloaded
local tokenizer.json files at the pinned releases. The verifier never calls a model.
"""

import argparse
import ast
from collections import Counter, defaultdict
from datetime import datetime
from hashlib import sha256
from importlib.machinery import PathFinder
import importlib.util
import json
import os
from pathlib import Path
import platform
import random
import re
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prior = load_file("adaptive_archive_verifier", HERE.parent / "adaptive/verify_adaptive.py")
audit = prior.audit
require = audit.require
# Pinned from local sources, model manifests and fixtures before scored calls.
FILES = "a4ab4dd5e9f463480e64f799be6d46197e1d37aa842117fdeaebb6638e43d2e1"
CORPUS = "9ca35dd5fc366a0b970bc18903d61195444df1c4a98f95bc1c3a069543fac687"
STAR = "starcoder2:3b"
STAR_MODEL = "f67ae0f64584a4d1d7c609bf4778dd0d07054582362d21ca4f0eddea22aafd0c"
STAR_TOKENIZER = "6190a6649d90a7fe35bfed8bff990c3e7aafc3cfa5beea185045f03f0890402b"
MODELS = (audit.MODEL, STAR)
ARMS = ("gpp_rules", "gpp_guard", "gpp_full", "python_guard", "python_full", "rust_guard", "rust_full")
RULE_STOPS = ["\nelse", "\n#", chr(96) * 3]
STAR_STOPS = ["<file_sep>", "<fim_prefix>", "<fim_suffix>", "<fim_middle>", "<|endoftext|>"]


def check_files(meta, study_name="multi-caller-policy-v7", file_map=FILES):
    require(meta["type"] == "metadata" and meta["study"] == study_name, "wrong archive")
    require(audit.json_digest(meta["file_sha256"]) == file_map, "dependency roster or fingerprint differs")
    for path, digest in meta["file_sha256"].items():
        require(audit.digest(ROOT / path) == digest, f"changed dependency {path}")
    require(audit.digest(audit.GPP) == meta["gpp_sha256"] == audit.COMPILER, "compiler differs")
    require(meta["model_digests"] == {audit.MODEL: audit.MODEL_DIGEST, STAR: STAR_MODEL}, "model digest differs")
    require(sha256(meta["model_template"].encode()).hexdigest() == audit.TEMPLATE
            and meta["star_template"] == "{{ .Prompt }}" and meta["star_transport"] == "raw-prefix-suffix-middle",
            "model template or transport differs")
    require(all(meta[k] == v for k, v in prior.VERSIONS.items()), "software/host metadata differs")


def fixtures(name="fresh"):
    # A globally installed third-party distribution named bench can otherwise
    # override the repository's namespace package when retokenizing outside the venv.
    local = PathFinder.find_spec("bench", [str(ROOT)])
    with patch.dict(sys.modules, {"bench": importlib.util.module_from_spec(local)}):
        return load_file("checked_policy_fixtures", HERE / (name + ".py")).TASKS


def check_manifest(meta, tasks, corpus=CORPUS, n_tasks=8, counts=(24, 104)):
    require(len(tasks) == len({t["id"] for t in tasks}) == n_tasks, "invalid task count")
    require(audit.json_digest(tasks) == meta["corpus_sha256"] == corpus, "fixture fingerprint differs")
    require(meta["tasks"] == [t["id"] for t in tasks] and meta["sources"] == {
        t["id"]: {k: t[k] for k in ("source_url", "provenance")} for t in tasks}, "task roster/provenance differs")
    sizes = tuple(sum(len(t[k]) for t in tasks) for k in ("public", "heldout"))
    require(sizes == (meta["public_cases"], meta["hidden_cases"]) == counts
            and meta["reference_cases_checked"] == 3 * sum(sizes), "oracle or preflight size differs")
    require(meta["models"] == list(MODELS) and meta["seeds"] == [42] and meta["conditions"] == list(ARMS)
            and meta["order_seed"] == 18591 and meta["primary"] == "gpp_rules"
            and meta["primary_comparator"] == "python_guard", "study assignment differs")
    require(meta["model_options"] == audit.OPTIONS and meta["default_stops"] == []
            and meta["model_default_stops"] == {m: [] for m in MODELS} and meta["star_stops"] == STAR_STOPS
            and meta["rule_stops"] == RULE_STOPS and meta["boundary_stops"] == audit.STOPS, "decoding defaults differ")
    require(datetime.fromisoformat(meta["started_at"]).tzinfo is not None, "missing zoned start time")
    order = []
    for model in MODELS:
        rng = random.Random(18591)
        shuffled = list(tasks)
        rng.shuffle(shuffled)
        for task in shuffled:
            arms = list(ARMS)
            rng.shuffle(arms)
            order.extend((model, 42, task["id"], arm) for arm in arms)
    return order


def serialized(model, prompt, suffix):
    if model == STAR:
        return f"<fim_prefix>{prompt}<fim_suffix>{suffix}<fim_middle>"
    return f"<|fim_prefix|>{prompt}<|fim_suffix|>{suffix}<|fim_middle|>"


def check_request(study, task, row, base, attempt, previous):
    model, arm, lang = row["model"], row["condition"], row["language"]
    failure = (previous["response"], previous["public_detail"]) if previous else None
    prompt, suffix = study.render(task, arm, base, failure)
    require((prompt, suffix) == (attempt["prompt"], attempt["suffix"]), "prompt or suffix differs")
    retry = previous is not None
    require(attempt["caller_context"] is retry and ("Read-only caller excerpts:" in prompt) == retry,
            "caller context differs")
    check_wire(study, model, arm, prompt, suffix, attempt, retry)


def check_wire(study, model, arm, prompt, suffix, attempt, retry):
    stops = RULE_STOPS if arm == "gpp_rules" else audit.STOPS[arm.split("_")[0]]
    opts = dict(audit.OPTIONS, stop=(STAR_STOPS if model == STAR else []) + stops)
    if retry:
        opts.update(seed=43, temperature=0.25)
    require(opts == attempt["sampling"], "sampling/stop settings differ")
    expected = dict(model=model, stream=False, keep_alive="3m", options=opts)
    if model == STAR:
        expected.update(raw=True, prompt=serialized(model, prompt, suffix))
    else:
        expected.update(prompt=prompt, suffix=suffix)
    # Intercept the frozen generator at its network boundary to verify the
    # complete wire request shape without contacting a live inference service.
    with patch.object(study.pilot, "request", return_value={}) as offline:
        _, actual = study.generate(model, arm, prompt, suffix, [], retry)
        require(offline.call_count == 1 and offline.call_args.args == ("generate", expected)
                and not offline.call_args.kwargs and actual == opts, "wire request construction differs")


def check_trial(study, task, row, base, request_checker=check_request, durations=("load_ms", "generation_ms")):
    arm, lang = row["condition"], row["language"]
    require((arm.split("_")[0], "maintenance", "body") == (lang, row["kind"], row["form"]), "trial labels differ")
    calls = row["attempts"]
    require(len(calls) in (1, 2), "call count outside retry budget")
    for i, a in enumerate(calls):
        request_checker(study, task, row, base, a, calls[i-1] if i else None)
        require(isinstance(a["response"], str) and isinstance(a["public_detail"], str), "response/detail missing")
        for field, low, high in (("input_tokens", 1, 2048), ("output_tokens", 0, 240)):
            require(type(a[field]) is int and low <= a[field] <= high, f"{field} outside assigned budget")
        require(a["output_tokens"] or not a["response"], "text with zero generated tokens")
        require(a["done_reason"] in {"length", "stop"} and (a["done_reason"] != "length" or a["output_tokens"] == 240),
                "unexpected generation termination")
        require(all(audit.finite_ms(a[k]) for k in ("model_ms", "tool_ms", *durations)),
                "invalid duration")
        status, detail, entry = a["public_outcome"], a["public_detail"], a["public_failed_entry"]
        require(status in {"pass", *audit.ERRORS} and bool(detail) == (status != "pass"), "invalid public result")
        if a["stage"] == "patch":
            require(status == "check_error" and entry is None and a["patch_sha256"] is None, "invalid patch rejection")
        else:
            require(a["stage"] == "public" and re.fullmatch("[0-9a-f]{64}", a["patch_sha256"] or ""),
                    "invalid patch fingerprint")
        if entry is not None:
            require(entry in {e for e, _, _ in task["public"]} and status in {"wrong_answer", "runtime_error"},
                    "unattributable public failure")
        for name, args, _ in task["public"]:
            call = f"{name}({study.arguments(args, lang)})"
            if detail.startswith((call + " returned ", call + " failed during execution.")):
                require(entry == name, "failure entry disagrees with diagnostic")
        if status == "pass":
            require(i == len(calls)-1 and a["outcome"] in {"accepted", *("heldout_" + e for e in audit.ERRORS)},
                    "invalid hidden outcome or spurious retry")
        else:
            require(a["outcome"] == status, "relabelled public failure")
        if not i:
            trigger = status != "pass" and entry is not None and entry != task["target"]
            require((len(calls) == 2) == trigger, "first public caller-failure retry gate differs")
    accepted = calls[-1]["outcome"] == "accepted"
    require(row["accepted"] is accepted and row["first_accepted"] is (accepted and len(calls) == 1),
            "acceptance flags differ")
    require(audit.finite_ms(row["heldout_ms"]) and isinstance(row["heldout_detail"], str), "invalid hidden timing")
    if calls[-1]["public_outcome"] == "pass":
        require(row["heldout_ms"] > 0 and bool(row["heldout_detail"]) != accepted, "missing hidden result")
    else:
        require(row["heldout_ms"] == 0 and not row["heldout_detail"], "unexpected hidden evaluation")
    require(audit.finite_ms(row["wall_ms"]) and row["wall_ms"] + .01 >= sum(a["tool_ms"]+a["model_ms"] for a in calls),
            "workflow duration shorter than model/public checks")


def statements(source, language):
    if language == "python":
        # Keep the original suite indentation. A flush-left comment inside a
        # function can prevent dedent from identifying its statement margin.
        tree = ast.parse("def _checked_target():\n" + source)
        return [ast.dump(s) for s in tree.body[0].body]
    from fragments import _brace_tokens
    return [s for s, _, _ in _brace_tokens(source)]


def replay(study, tools, task, row, base):
    lang, arm = row["language"], row["condition"]
    original = study.functions(base, lang)
    target = original[task["target"]]
    for i, a in enumerate(row["attempts"], 1):
        public, diag, code = study.patch(tools, task, arm, base, a["response"])
        stage, entry = ("public" if public == "pass" else "patch"), None
        require((stage, sha256(code.encode()).hexdigest() if code else None) == (a["stage"], a["patch_sha256"]),
                f"call {i}: patch stage or digest differs")
        if public == "pass":
            new = study.functions(code, lang)
            require(list(new) == list(original) and new[target.name].signature == target.signature
                    and code.startswith(base[:target.start]) and code.endswith(base[target.end:]),
                    f"call {i}: changed caller bytes or target signature")
            if not arm.endswith("_full"):
                kept = statements(target.body, lang)
                after = statements(new[target.name].body, lang)
                require(kept and after[-len(kept):] == kept, f"call {i}: protected starter statements changed")
            public, diag, entry = study.previous.public_evaluate(tools, lang, code, task["public"])
        require((public, diag, entry) == (a["public_outcome"], a["public_detail"], a["public_failed_entry"]),
                f"call {i}: replayed public outcome/diagnostic/entry differs: {(public, diag, entry)!r}")
        if public == "pass":
            hidden, diag = study.evaluate(tools, lang, code, task["heldout"], already_checked=True)
            terminal = "accepted" if hidden == "pass" else "heldout_" + hidden
            require((terminal, diag) == (a["outcome"], row["heldout_detail"]),
                    f"call {i}: replayed hidden outcome/diagnostic differs: {(hidden, diag)!r}")


def tokenizers(qwen, star):
    encoders = {}
    for model, path, expected in [(audit.MODEL, qwen, audit.TOKENIZER), (STAR, star, STAR_TOKENIZER)]:
        if path:
            from tokenizers import Regex, Tokenizer, pre_tokenizers
            require(audit.digest(path) == expected, f"{model}: independent tokenizer fingerprint differs")
            released = Tokenizer.from_file(str(path))
            installed = released
            if model == STAR:
                # This pinned 2024 GGUF lacks tokenizer.ggml.pre. Ollama v0.6.2
                # selects llama.cpp's default BPE pretokenizer in that case.
                # Reuse the publisher's vocabulary, BPE merge ranks and special
                # tokens. Report the unmodified publisher tokenizer separately.
                # https://github.com/ollama/ollama/blob/v0.6.2/llama/llama.cpp/src/llama-vocab.cpp
                installed = Tokenizer.from_file(str(path))
                splits = [r"[\p{P}\$\+<=>\^~\|]+",
                          r"'s|'t|'re|'ve|'m|'ll|'d| ?\p{L}+| ?\p{N}+| ?[^\s\p{L}\p{N}]+|\s+(?!\S)",
                          r"\p{N}+", r"[0-9][0-9][0-9]"]
                installed.pre_tokenizer = pre_tokenizers.Sequence([
                    *(pre_tokenizers.Split(Regex(p), behavior="isolated") for p in splits),
                    pre_tokenizers.ByteLevel(add_prefix_space=False, use_regex=False),
                ])
            encoders[model] = installed, released
    return encoders


def replay_tools(study, meta):
    tools = study.Tools(ROOT, audit.GPP)
    require(platform.python_version() == meta["python"] and platform.platform() == meta["host"],
            "replay host or Python version differs")
    for key, cmd in (("mypy", [tools.python, "-m", "mypy", "--version"]), ("rust", [tools.rustc, "--version"])):
        require(subprocess.check_output(cmd, text=True).strip() == meta[key], f"installed {key} differs")
    directory = Path(os.environ.get("OLLAMA_MODELS", Path.home() / ".ollama/models"))
    for model in MODELS:
        name, tag = model.split(":")
        manifest = directory / "manifests/registry.ollama.ai/library" / name / tag
        require(audit.digest(manifest) == meta["model_digests"][model], f"{model}: installed manifest differs")
    tools.canaries()
    return tools


def check_report(log, path, totals, selected=None):
    rendered = subprocess.check_output([sys.executable, "-B", HERE / "report_policy.py", log], text=True)
    require(path.read_text(encoding="utf-8") == rendered, "archived report differs from a fresh rendering")
    for model in MODELS:
        lines = rendered.split("## " + model + "\n", 1)[1].split("\n## ", 1)[0].splitlines()
        for arm in ARMS:
            c = totals[model, arm]
            n, wins, first = c["assigned"], c["accepted"], c["first"]
            tokens = c["input"] + c["output"]
            raw = [arm, first, audit.num(audit.divide(c["first_tokens"], first)), c["calls"]-n,
                   wins-first, tokens-c["first_tokens"], f"{wins}/{n}", c["input"], c["output"],
                   audit.num(audit.divide(tokens, wins)), audit.num(audit.divide(c["wall_ms"]/1000, wins))]
            require(audit.mdrow(raw) in lines, f"{model}/{arm}: independent report totals differ")
            primary = selected[model]["gpp"] if selected else "gpp_rules"
            if arm == primary:
                continue
            left = totals[model, primary]
            left_wins, left_tokens = left["accepted"], left["input"] + left["output"]
            paired = next((line for line in lines if line.startswith(f"| {arm} | {n}/{n} | {n} | ")), None)
            ratio = left_tokens*wins / (left_wins*tokens) if left_wins and wins else None
            time_ratio = left["wall_ms"]*wins / (left_wins*c["wall_ms"]) if left_wins and wins else None
            points = [100*(left_wins-wins)/n, left_tokens/tokens, ratio, time_ratio]
            require(paired and [s.strip().split()[0] for s in paired.strip("|").split("|")[3:7]]
                    == [audit.num(x, 4) for x in points], f"{model}/{arm}: paired point estimate differs")
            goal = .8*tokens/wins if wins else None
            require(audit.mdrow([arm, audit.num(goal), audit.num(100*(1-ratio) if ratio is not None else None),
                                audit.num(100*(ratio-.8) if ratio is not None else None),
                                audit.num(left_tokens/left_wins-goal if ratio is not None else None)]) in lines,
                    f"{model}/{arm}: distance from 20% goal differs")


def verify(log, do_replay, qwen, star, report_file):
    data = log.read_bytes()
    meta, *rows = map(json.loads, data.splitlines())
    check_files(meta)
    import run_policy as study
    tasks = fixtures()
    order = check_manifest(meta, tasks)
    require([(r["model"], r["seed"], r["task"], r["condition"]) for r in rows] == order,
            "incomplete, repeated, unexpected or reordered assignment")
    by_task = {t["id"]: t for t in tasks}
    bases = {}
    for t in tasks:
        for lang in ("gpp", "rust", "python"):
            base = study.source_for(t, lang)
            prior.check_public_reachability(study.previous, t, lang, base)
            bases[t["id"], lang] = base
    encoders = tokenizers(qwen, star)
    tools = replay_tools(study, meta) if do_replay else None
    totals = defaultdict(Counter)
    for row in rows:
        task, arm, model = by_task[row["task"]], row["condition"], row["model"]
        base = bases[task["id"], row["language"]]
        try:
            check_trial(study, task, row, base)
            if tools:
                replay(study, tools, task, row, base)
            count = totals[model, arm]
            count["assigned"] += 1
            count["accepted"] += row["accepted"]
            count["first"] += row["first_accepted"]
            initial = row["attempts"][0]
            count["first_tokens"] += initial["input_tokens"] + initial["output_tokens"]
            count["wall_ms"] += row["wall_ms"]
            count["recovered"] += row["accepted"] and len(row["attempts"]) == 2
            for a in row["attempts"]:
                count["calls"] += 1
                count["input"] += a["input_tokens"]
                count["output"] += a["output_tokens"]
                count["hidden"] += a["public_outcome"] == "pass"
                count["patched"] += a["stage"] == "public"
                if model in encoders:
                    text = serialized(model, a["prompt"], a["suffix"])
                    installed, released = encoders[model]
                    length = len(installed.encode(text).ids)
                    require(min(length, 2048) == a["input_tokens"],
                            f"independent tokenizer counted {length}, server recorded {a['input_tokens']}")
                    count["retokenized"] += 1
                    count["truncated"] += length > 2048
                    if model == STAR:
                        upstream = len(released.encode(text).ids)
                        count["publisher_tokens"] += upstream
                        count["publisher_differences"] += upstream != length
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError(f"{model}/{task['id']}/{arm}: {exc}") from exc
    if report_file:
        check_report(log, report_file, totals)
    require(data == log.read_bytes(), "archive changed during verification")
    for model in MODELS:
        for arm in ARMS:
            c = totals[model, arm]
            print(f"{model} {arm}: {c['accepted']}/{c['assigned']} accepted, {c['calls']} calls, "
                  f"{c['input']} input + {c['output']} output = {c['input']+c['output']} tokens")
        c = sum((totals[model, arm] for arm in ARMS), Counter())
        print(f"{model}: {dict(c)}")
    c = sum(totals.values(), Counter())
    print(f"Verified {c['assigned']} assignments, {c['calls']} calls and {c['accepted']} accepts.")
    if do_replay:
        print(f"Replayed {c['calls']} patch decisions, {c['patched']} public evaluations and {c['hidden']} hidden "
              "evaluations; all original digests, immutable callers, fallback suffixes, gate decisions and diagnostics matched.")
    print(f"Archive SHA-256: {sha256(data).hexdigest()}")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("log", type=Path)
    cli.add_argument("--replay", action="store_true", help="rescore every archived completion in the frozen sandbox")
    cli.add_argument("--qwen-tokenizer", type=Path, help="Qwen2.5-Coder-7B-Instruct tokenizer.json at c03e6d358207")
    cli.add_argument("--star-tokenizer", type=Path, help="BigCode StarCoder2-3B tokenizer.json at 54da76775f65")
    cli.add_argument("--report", type=Path, help="compare a saved report with independent totals and a fresh rendering")
    args = cli.parse_args()
    try:
        verify(args.log, args.replay, args.qwen_tokenizer, args.star_tokenizer, args.report)
    except (ValueError, KeyError, TypeError, OSError, ImportError, subprocess.CalledProcessError) as err:
        cli.exit(1, f"{err}\n")
