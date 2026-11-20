"""Verify the v5 maintenance log and independently recompute its report totals.

Use --replay under the study Python environment to run the frozen evaluator.
Optional --tokenizer takes the local Qwen2.5-Coder-7B-Instruct tokenizer.json
at revision c03e6d358207e414f1eca0bb1891e29f1db0e242 and requires tokenizers.
This command runs offline.
"""

import argparse
from collections import Counter
from hashlib import sha256
import importlib.util
import json
import math
from pathlib import Path
import platform
import random
import re
import subprocess
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
GPP = ROOT / "target/debug/gpp"

# Captured independently before inference. The file map hash locks the complete
# set of relative paths as well as the individual digests.
FILES = "edb208ce922b46f06e5b7103a6aa1c353d37b4e0ba6535d71cca369a2e9702ef"
CORPUS = "c3bb69063fc6b1fdd88888217da1773b163df44672f27961ed3b572eecd5b3b2"
COMPILER = "c245a91b44a5f5dd77c41b72d414915fc0a82ed69e501118f24317c286c8760c"
MODEL = "qwen2.5-coder:7b"
MODEL_DIGEST = "dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364"
TEMPLATE = "1e65450c30670713aa47fe23e8b9662bdf4065e81cc8e3cbfaa98924fcc0d320"
TOKENIZER = "c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539"
ARMS = ("gpp_context", "python_context", "rust_context", "gpp_target", "gpp_projected")
COMPARISONS = (("gpp_context", "python_context"), ("gpp_context", "rust_context"),
               ("gpp_context", "gpp_target"), ("gpp_projected", "python_context"),
               ("gpp_projected", "rust_context"))
OPTIONS = {"seed": 42, "temperature": 0, "num_ctx": 2048, "num_predict": 240}
STOPS = {"gpp": ["\n}"], "rust": ["\n}"],
         "python": ["\ndef ", "\nclass ", "\nimport ", "\nfrom ", "\nassert ", "\nprint(", "\nif __name__", "\n@"]}
ERRORS = {"check_error", "runtime_error", "wrong_answer"}


def require(yes, message):
    if not yes:
        raise ValueError(message)


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def json_digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_runner():
    # Its transitive imports include bench/empirical/run.py under the name run.
    # Keep the two modules distinct.
    sys.path.insert(0, str(HERE))
    spec = importlib.util.spec_from_file_location("maintenance_study_runner", HERE / "run.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    return runner


def check_files(meta):
    require(meta["type"] == "metadata" and meta["study"] == "multi-caller-maintenance-v5", "wrong manifest")
    require(json_digest(meta["file_sha256"]) == FILES, "archived dependency roster or fingerprint changed")
    for rel, expected in meta["file_sha256"].items():
        require(digest(ROOT / rel) == expected, f"modified dependency: {rel}")
    require(digest(GPP) == meta["gpp_sha256"] == COMPILER, "compiler binary fingerprint changed")


def check_manifest(meta, tasks):
    require(meta["models"] == [MODEL] and meta["seeds"] == [42], "unexpected model or seed")
    require(meta["model_digests"] == {MODEL: MODEL_DIGEST}, "model manifest fingerprint changed")
    require(sha256(meta["model_template"].encode()).hexdigest() == TEMPLATE, "model template changed")
    require(meta["ollama_version"] == "0.6.2", "unexpected model server version")
    require(meta["model_options"] == OPTIONS and meta["default_stops"] == []
            and meta["boundary_stops"] == STOPS, "default sampling options changed")
    require(meta["conditions"] == list(ARMS) and meta["primary_comparator"] == "python_context"
            and meta["order_seed"] == 11839, "assignment configuration changed")
    require(len(tasks) == len({t["id"] for t in tasks}) == 8, "invalid eight-task corpus")
    require(meta["tasks"] == [t["id"] for t in tasks] and meta["corpus_sha256"] == json_digest(tasks) == CORPUS,
            "corpus content or order changed")
    require(meta["sources"] == {t["id"]: {k: t[k] for k in ("source_url", "provenance")} for t in tasks},
            "task provenance differs")
    n_public, n_hidden = [sum(len(t[k]) for t in tasks) for k in ("public", "heldout")]
    require((n_public, n_hidden) == (meta["public_cases"], meta["hidden_cases"]) == (28, 128),
            "oracle size differs")
    require(meta["reference_cases_checked"] == 3 * (n_public + n_hidden), "reference preflight count differs")
    rng = random.Random(11839)
    task_order = list(tasks)
    rng.shuffle(task_order)
    assignments = []
    for task in task_order:
        arms = list(ARMS)
        rng.shuffle(arms)
        assignments.extend((MODEL, 42, task["id"], arm) for arm in arms)
    return assignments


def finite_ms(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def check_trial(study, row, task):
    arm, lang = row["condition"], row["language"]
    surface = "python" if arm == "gpp_projected" else lang
    require((lang, row["kind"], row["form"]) == (arm.split("_")[0], task["kind"], task["form"]),
            "trial labels differ")
    calls = row["attempts"]
    require(len(calls) in (1, 2), "invalid call budget")
    base = study.source_for(task, lang)
    previous = feedback = None
    for i, a in enumerate(calls):
        opts = dict(OPTIONS, stop=STOPS[surface])
        if i:
            opts.update(seed=43, temperature=0.25)
        require(a["sampling"] == opts, "sampling or stop settings differ")
        rendered = study.render(task, arm, base, previous, feedback)
        require((a["prompt"], a["suffix"], surface) == rendered, "rendered prompt, feedback or suffix differs")
        require(isinstance(a["response"], str) and isinstance(a["public_detail"], str), "missing response/feedback")
        for field, limit in (("input_tokens", "num_ctx"), ("output_tokens", "num_predict")):
            require(type(a[field]) is int and 0 < a[field] <= opts[limit], f"{field} outside limits")
        require(a["done_reason"] in {"stop", "length"} and
                (a["done_reason"] != "length" or a["output_tokens"] == opts["num_predict"]),
                "invalid generation termination")
        require(all(finite_ms(a[k]) for k in ("model_ms", "tool_ms", "load_ms", "generation_ms")),
                "invalid attempt duration")
        public, outcome = a["public_outcome"], a["outcome"]
        if a["stage"] == "patch":
            require(public == "check_error" and a["patch_sha256"] is None, "invalid patch failure")
        else:
            require(a["stage"] == "public" and isinstance(a["patch_sha256"], str)
                    and re.fullmatch(r"[0-9a-f]{64}", a["patch_sha256"]), "invalid patched source signature")
        if public == "pass":
            require(i + 1 == len(calls) and outcome in {"accepted", *("heldout_" + x for x in ERRORS)}
                    and a["public_detail"] == "", "invalid public success or hidden result")
        else:
            require(public in ERRORS and outcome == public and a["public_detail"], "invalid public failure")
        previous, feedback = a["response"], a["public_detail"]
    public_pass = calls[-1]["public_outcome"] == "pass"
    accepted = calls[-1]["outcome"] == "accepted"
    require(row["accepted"] is accepted and row["first_accepted"] is (len(calls) == 1 and accepted),
            "trial verdict inconsistent")
    require(finite_ms(row["heldout_ms"]) and isinstance(row["heldout_detail"], str), "invalid hidden measurement")
    if public_pass:
        require(row["heldout_ms"] > 0 and bool(row["heldout_detail"]) != accepted, "missing hidden evaluation")
    else:
        require(len(calls) == 2 and row["heldout_ms"] == 0 and row["heldout_detail"] == "",
                "missing repair or unexpected hidden evaluation")
    require(finite_ms(row["wall_ms"]) and row["wall_ms"] + .01 >= sum(a["model_ms"] + a["tool_ms"] for a in calls),
            "workflow duration inconsistent with attempt durations")
    return base, surface


def replay(study, tools, row, task, base, surface):
    lang = row["language"]
    target = study.functions(base, lang)[task["target"]]
    for i, a in enumerate(row["attempts"], 1):
        status, detail, code = study.materialize(tools, task, lang, surface, base, a["response"])
        stage = "public" if status == "pass" else "patch"
        require(stage == a["stage"], f"call {i}: patch stage differs")
        require((sha256(code.encode()).hexdigest() if code else None) == a["patch_sha256"],
                f"call {i}: patched source fingerprint differs")
        if status == "pass":
            require(code.startswith(base[:target.start]) and code.endswith(base[target.end:]), "caller bytes changed")
            require(study.functions(code, lang)[target.name].signature == target.signature, "signature changed")
            status, detail = study.evaluate(tools, lang, code, task["public"])
        require((status, detail) == (a["public_outcome"], a["public_detail"]),
                f"call {i}: replayed public result or diagnostic differs: {(status, detail)!r}")
        if status == "pass":
            hidden, detail = study.evaluate(tools, lang, code, task["heldout"], already_checked=True)
            final = "accepted" if hidden == "pass" else "heldout_" + hidden
            require((final, detail) == (a["outcome"], row["heldout_detail"]),
                    f"call {i}: replayed hidden result or diagnostic differs: {(final, detail)!r}")


def retokenize(path, attempts):
    from tokenizers import Tokenizer
    require(digest(path) == TOKENIZER, "independent Qwen tokenizer fingerprint changed")
    encoder = Tokenizer.from_file(str(path))
    truncated = 0
    for i, a in enumerate(attempts, 1):
        rendered = f"<|fim_prefix|>{a['prompt']}<|fim_suffix|>{a['suffix']}<|fim_middle|>"
        length = len(encoder.encode(rendered).ids)
        require(min(length, OPTIONS["num_ctx"]) == a["input_tokens"], f"call {i}: retokenized input differs")
        truncated += length > OPTIONS["num_ctx"]
    print(f"Independently retokenized {len(attempts)} FIM inputs; {truncated} exceeded the input window.")


def num(n, digits=2):
    return "undefined" if n is None else f"{n:,.{digits}f}"


def divide(x, y):
    return x / y if y else None


def mdrow(cells):
    return "| " + " | ".join(map(str, cells)) + " |"


def check_report(log, rows, saved):
    report = subprocess.check_output([sys.executable, "-B", HERE / "report.py", log], text=True)
    if saved:
        require(saved.read_text(encoding="utf-8").rstrip() == report.rstrip(), "saved report differs from fresh rendering")
    totals = {}
    lines = report.splitlines()
    for arm in ARMS:
        group = [r for r in rows if r["condition"] == arm]
        n = len(group)
        calls = [a for r in group for a in r["attempts"]]
        first, wins = [sum(r[k] for r in group) for k in ("first_accepted", "accepted")]
        inputs, outputs = [sum(a[k] for a in calls) for k in ("input_tokens", "output_tokens")]
        tokens = inputs + outputs
        seconds = sum(r["wall_ms"] for r in group) / 1000
        totals[arm] = wins, tokens, seconds
        rates = [f"{x}/{n} ({100*x/n:.1f}%)" for x in (first, wins)]
        line = mdrow([arm, len(calls), *rates, inputs, outputs, tokens, num(divide(tokens, wins)),
                      num(divide(seconds, wins))])
        require(line in lines, f"independently computed totals differ for {arm}")
        initial = sum(r["attempts"][0][k] for r in group for k in ("input_tokens", "output_tokens"))
        require(mdrow([arm, initial, first, num(divide(initial, first)), len(calls)-n, tokens-initial,
                       wins-first]) in lines, f"repair totals differ for {arm}")
        print(f"{arm}: {wins}/{n} accepted, {len(calls)} calls, {inputs}+{outputs}={tokens} tokens")
    for left, right in COMPARISONS:
        lw, lt, ls = totals[left]
        rw, rt, rs = totals[right]
        cost = lt*rw/(lw*rt) if lw and rw else None
        points = (100*(lw-rw)/8, lt/rt, cost, ls*rw/(lw*rs) if lw and rw and rs else None)
        pair = next((line for line in lines if line.startswith(f"| {left} | {right} | 8/8 | 8 |")), None)
        require(pair is not None and [s.strip().split()[0] for s in pair.strip("|").split("|")[4:8]]
                == [num(p, 4) for p in points], f"paired point estimate differs for {left}/{right}")
        if right == "gpp_target":
            continue
        target = divide(.80*rt, rw)
        need = max(math.ceil(lt/target), math.ceil(rw-.02*8)) if target is not None else None
        minimum = "undefined" if need is None else (str(need) if need <= 8 else f"{need} required with 8 assigned")
        reduction = max(0, 100*(1-target*lw/lt)) if lw and target is not None else None
        gap = 100*(cost-.80) if cost is not None else None
        require(mdrow([left, right, num(target), num(cost, 3), num(gap, 1), num(reduction, 1), minimum]) in lines,
                f"distance to target differs for {left}/{right}")


def verify(log, do_replay, saved, tokenizer_path):
    data = log.read_bytes()
    meta, *rows = map(json.loads, data.splitlines())
    check_files(meta)
    study = load_runner()
    tasks = study.workload()
    observed = [(r["model"], r["seed"], r["task"], r["condition"]) for r in rows]
    require(observed == check_manifest(meta, tasks), "incomplete, duplicate, unknown or reordered assignment")
    fixtures = {t["id"]: t for t in tasks}
    tools = None
    if do_replay:
        tools = study.Tools(ROOT, GPP)
        require(platform.python_version() == meta["python"], "replay Python version differs")
        for tool, cmd in (("rust", [tools.rustc, "--version"]), ("mypy", [tools.python, "-m", "mypy", "--version"])):
            require(subprocess.check_output(cmd, text=True).strip() == meta[tool], f"replay {tool} version differs")
        tools.canaries()
    for row in rows:
        task = fixtures[row["task"]]
        try:
            base, surface = check_trial(study, row, task)
            if do_replay:
                replay(study, tools, row, task, base, surface)
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError(f"{task['id']}/{row['condition']}: {exc}") from exc
    attempts = [a for r in rows for a in r["attempts"]]
    if tokenizer_path:
        retokenize(tokenizer_path, attempts)
    check_report(log, rows, saved)
    require(log.read_bytes() == data, "log changed during verification")
    print(f"Verified {len(rows)} assigned trials, {len(attempts)} calls and {sum(r['accepted'] for r in rows)} accepts.")
    if do_replay:
        print(f"Replayed {len(attempts)} completions and {sum(a['public_outcome']=='pass' for a in attempts)} "
              "held-out evaluations. Every stage, patch hash, outcome and diagnostic matched.")
    print(f"Generation terminations: {dict(Counter(a['done_reason'] for a in attempts))}")
    print(f"Log SHA-256: {sha256(data).hexdigest()}")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("log", type=Path)
    cli.add_argument("--report", type=Path, help="compare the archived Markdown to a fresh rendering")
    cli.add_argument("--replay", action="store_true", help="rescore all attempts in the study sandbox")
    cli.add_argument("--tokenizer", type=Path, help="retokenize all FIM inputs with pinned local Qwen tokenizer.json")
    args = cli.parse_args()
    try:
        verify(args.log, args.replay, args.report, args.tokenizer)
    except (ValueError, KeyError, OSError, TypeError, ImportError, subprocess.CalledProcessError) as err:
        cli.exit(1, f"{err}\n")
