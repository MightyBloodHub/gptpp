"""Paired, local-model scalar authoring experiment."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import random
import re
import subprocess
import time
from urllib.request import urlopen

from evaluate import Tools, arguments, signature
from maintenance import TASKS as MAINTENANCE
from synthesis import TASKS as SYNTHESIS


ROOT = Path(__file__).resolve().parents[2]
MODELS = ("deepseek-coder:6.7b", "llama3:latest")
LANGUAGES = ("gpp", "python", "rust")
LABELS = {"gpp": "GPT++", "python": "Python 3.11", "rust": "Rust 2024"}
GUIDES = {
    "gpp": (
        "GPT++ scalar syntax: fn example(x: I64, flag: Bool) -> I64 !{} { "
        "var n = x; if flag { n = n + 1; } while n < 0 { n = n + 2; } return n; }. "
        "let is immutable; var allows reassignment. Blocks use braces and statements end in semicolons. "
        "Use true/false, &&, ||, !, and + - * / %. Signed division truncates toward zero. "
        "Only if/else and while are available for control flow. No for, break, arrays, methods, or imports."
    ),
    "python": (
        "Use built-in int and bool annotations. Use True/False, and/or/not, if/else, and loops. "
        "Use integer // and % deliberately because Python rounds down for negative division."
    ),
    "rust": (
        "Use i64 and bool. let is immutable and let mut allows reassignment. "
        "Use true/false, &&, ||, !, if/else, and loops. Signed division truncates toward zero."
    ),
}
SEED = 42
ORDER_SEED = 18119
OPTIONS = {"seed": SEED, "temperature": 0, "num_ctx": 2048, "num_predict": 240}
FENCE = re.compile(r"```[^\r\n]*[\r\n]+(.*?)(?:```|\Z)", re.DOTALL)


def request(endpoint, payload=None, timeout=90):
    from urllib.request import Request
    body = None if payload is None else json.dumps(payload).encode()
    req = Request(
        f"http://127.0.0.1:11434/api/{endpoint}", body,
        headers={"Content-Type": "application/json"},
    )
    with urlopen(req, timeout=timeout) as response:
        return json.load(response)


def make_prompt(task, language):
    cases = "\n".join(
        f"solve({arguments(args, language)}) returns {value}."
        for args, value in task["public"]
    )
    initial = (
        f"Write one function in {LABELS[language]}. Output only the complete function code. "
        "Use no dependencies, external resources, input, output, or entry point. "
        "The evaluator will call the required signature.\n"
        f"Signature: {signature(task, language)}\n\n"
        f"{GUIDES[language]}\n\n"
        f"Task: {task['description']}\n\nPublic examples:\n{cases}"
    )
    if task["kind"] == "maintenance":
        initial += f"\n\nModify this existing function as requested:\n{task['starter'][language]}"
    return initial


def candidate(response):
    fenced = FENCE.search(response)
    return (fenced.group(1) if fenced else response).strip()


def elapsed(start):
    return round((time.monotonic() - start) * 1000, 3)


def trial(tools, model, task, language):
    start = time.monotonic()
    initial = make_prompt(task, language)
    prompt = initial
    attempts = []
    for _ in range(2):
        model_start = time.monotonic()
        reply = request("generate", {
            "model": model, "prompt": prompt, "stream": False,
            "keep_alive": "2m", "options": OPTIONS,
        })
        model_ms = elapsed(model_start)
        code = candidate(reply["response"])
        tool_start = time.monotonic()
        public, detail = tools.evaluate(task, language, code, task["public"])
        attempts.append({
            "input_tokens": reply["prompt_eval_count"], "output_tokens": reply["eval_count"],
            "model_ms": model_ms, "tool_ms": elapsed(tool_start), "outcome": public,
            "load_ms": reply["load_duration"] / 1_000_000,
            "prompt_eval_ms": reply["prompt_eval_duration"] / 1_000_000,
            "generation_ms": reply["eval_duration"] / 1_000_000,
            "done_reason": reply.get("done_reason"), "prompt": prompt, "response": reply["response"],
            "public_outcome": public, "public_detail": detail,
        })
        if public == "pass":
            break
        prompt = (
            f"{initial}\n\nYour previous function:\n{code}\n\n"
            f"Public evaluator feedback:\n{detail}\n\nReturn the complete corrected function only."
        )

    workflow_ms = elapsed(start)
    accepted = False
    oracle_ms = 0
    oracle_detail = ""
    if public == "pass":
        oracle_start = time.monotonic()
        outcome, oracle_detail = tools.evaluate(
            task, language, code, task["heldout"], heldout=True
        )
        oracle_ms = elapsed(oracle_start)
        attempts[-1]["outcome"] = "accepted" if outcome == "pass" else f"heldout_{outcome}"
        accepted = outcome == "pass"
    return {
        "model": model, "task": task["id"], "kind": task["kind"], "language": language,
        "seed": SEED, "attempts": attempts, "accepted": accepted,
        "first_accepted": accepted and len(attempts) == 1,
        "wall_ms": workflow_ms, "heldout_ms": oracle_ms, "heldout_detail": oracle_detail,
    }


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def configuration(tools, tasks):
    files = [*ROOT.glob("src/*"), *ROOT.glob("spec/*")]
    files.extend(Path(__file__).parent / name for name in (
        "run.py", "evaluate.py", "synthesis.py", "maintenance.py"
    ))
    installed = {model["name"]: model["digest"] for model in request("tags")["models"]}
    return {
        "type": "metadata", "study": "scalar-authoring-pilot-v1",
        "models": MODELS, "tasks": [task["id"] for task in tasks],
        "languages": LANGUAGES, "seeds": [SEED], "order_seed": ORDER_SEED,
        "model_digests": {model: installed[model] for model in MODELS},
        "ollama_version": request("version")["version"], "model_options": OPTIONS,
        "max_attempts": 2, "holdout_total": sum(len(task["heldout"]) for task in tasks),
        "public_total": sum(len(task["public"]) for task in tasks),
        "host": platform.platform(),
        "cpu": subprocess.check_output(["/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip(),
        "python": platform.python_version(),
        "mypy": subprocess.check_output([tools.python, "-m", "mypy", "--version"], text=True).strip(),
        "rust": subprocess.check_output([tools.rustc, "--version"], text=True).strip(),
        "file_sha256": {str(p.relative_to(ROOT)): digest(p) for p in sorted(files) if p.is_file()},
        "gpp_sha256": digest(tools.gpp),
    }


def verified_cases(tools, tasks):
    status, detail = tools.evaluate(
        {"params": [("n", "int")]}, "python",
        "def solve(n: int) -> int:\n    return 'wrong type'\n",
        [((0,), 0)],
    )
    if status != "check_error" or "Incompatible return value type" not in detail:
        raise RuntimeError(f"Python baseline did not return its type diagnostic: {status}: {detail}")
    checks = 0
    for task in tasks:
        cases = task["public"] + task["heldout"]
        inputs = [tuple(args) for args, _ in cases]
        if len(set(inputs)) != len(cases) or len(task["heldout"]) < 15:
            raise RuntimeError(f"Invalid oracle case manifest for {task['id']}")
        for lang in LANGUAGES:
            status, detail = tools.evaluate(task, lang, task["reference"][lang], cases)
            if status != "pass":
                raise RuntimeError(f"Oracle calibration failed for {task['id']} {lang}: {detail}")
            if "starter" in task:
                status, detail = tools.evaluate(task, lang, task["starter"][lang], task["heldout"])
                if status != "wrong_answer":
                    raise RuntimeError(f"Starter probe for {task['id']} {lang}: {status}: {detail}")
            checks += len(cases)
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="JSONL data file. Resume only an identical manifest.")
    parser.add_argument("--gpp", type=Path, default=ROOT / "target/debug/gpp")
    args = parser.parse_args()
    tasks = [*SYNTHESIS, *MAINTENANCE]
    tools = Tools(ROOT, args.gpp)
    tools.canaries()
    # Verify all language-specific adapters and oracles before paying inference cost.
    config = json.loads(json.dumps(configuration(tools, tasks)))
    complete = {}
    if args.output.exists():
        with args.output.open() as old:
            metadata = json.loads(next(old))
            if any(metadata.get(key) != value for key, value in config.items()):
                raise RuntimeError("Run manifest changed. Use a new output file.")
            for line in old:
                row = json.loads(line)
                key = row["model"], row["task"], row["language"]
                if key in complete:
                    raise RuntimeError(f"Duplicate trial in existing run: {key}")
                complete[key] = row
    else:
        config["validated_reference_results"] = verified_cases(tools, tasks)
        config["started_at"] = datetime.now(timezone.utc).isoformat()
        print(f"Verified {config['validated_reference_results']} reference case results.", flush=True)
        with args.output.open("x") as out:
            print(json.dumps(config, sort_keys=True), file=out)

    rng = random.Random(ORDER_SEED)
    with args.output.open("a", buffering=1) as out:
        for model in MODELS:
            ordered = tasks.copy()
            rng.shuffle(ordered)
            for task in ordered:
                languages = list(LANGUAGES)
                rng.shuffle(languages)
                for language in languages:
                    key = model, task["id"], language
                    if key in complete:
                        continue
                    row = trial(tools, model, task, language)
                    print(json.dumps(row, ensure_ascii=False), file=out)
                    complete[key] = row
                    print(
                        f"{len(complete):02d}/72 {model} {task['id']} {language} "
                        f"{row['attempts'][-1]['outcome']} ({len(row['attempts'])} calls, "
                        f"{row['wall_ms'] / 1000:.2f}s)", flush=True,
                    )
    print("Acceptances:", dict(Counter(row["language"] for row in complete.values() if row["accepted"])))


if __name__ == "__main__":
    main()
