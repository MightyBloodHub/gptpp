"""Fresh paired infill replication using a model trained to complete source gaps."""

import argparse
import ast
import json
from datetime import datetime, timezone
from pathlib import Path
import platform
import random
import subprocess
import sys
import textwrap
import time

from run_study import HERE, Tools, fragment_trial, pilot, repair_feedback
from fragments import edited_function, old_fragment, prefix

sys.path.insert(0, str(pilot.ROOT / "tools"))
from scalar_fragment import lower_fragment

MODEL = "qwen2.5-coder:7b"
ORDER_SEED = 3321
CONDITIONS = ("gpp_fim", "gpp_chat", "gpp_projected", "python_fim", "rust_fim")


def infill_context(task, condition, previous=None, feedback=None):
    target = condition.split("_")[0]
    surface = "python" if condition == "gpp_projected" else target
    comment = "#" if surface == "python" else "//"
    lines = [task["description"]]
    examples = [f"{args} -> {value}" for args, value in task["public"]]
    lines.append("Examples: " + ", ".join(examples))
    if "starter" in task:
        lines.append("Previously:")
        lines.extend(old_fragment(task, target).splitlines())
    if condition == "gpp_projected":
        lines.append("Scalar Python syntax, checked I64. // truncates toward zero; % follows the dividend.")
    if condition == "gpp_fim":
        lines.append("GPT++ scalars: var for mutation; if b { x } else { y } for selection.")
    if previous is not None:
        lines.extend(["Previous attempt:", *previous.splitlines(), "Correct this error: " + feedback])
    context = "".join(f"{comment} {line}\n" for item in lines for line in item.splitlines())
    before = context + prefix(task, surface)
    if surface == "python":
        after = "\n\n# End of function\n"
    else:
        after = (";" if task["form"] == "expr" else "") + "\n}\n"
    return before, after


def materialize(tools, task, condition, raw):
    if condition != "gpp_projected":
        return edited_function(tools, task, condition.split("_")[0], raw)
    status, detail, py_function = edited_function(tools, task, "python", raw)
    if status != "pass":
        return status, detail, ""
    if task["form"] == "expr":
        fragment = ast.unparse(ast.parse(py_function).body[0].body[0].value)
    else:
        fragment = textwrap.dedent(py_function.split("\n", 1)[1]).strip()
    try:
        gpp = lower_fragment(fragment, task["form"], task["params"])
    except ValueError as exc:
        return "check_error", str(exc)[:600], ""
    return edited_function(tools, task, "gpp", gpp)


def trial(tools, task, condition, chat_template):
    lang = condition.split("_")[0]
    if condition == "gpp_chat":
        row = fragment_trial(tools, MODEL, task, lang, chat_template)
        row["condition"] = condition
        return row
    start = time.monotonic()
    previous = feedback = None
    attempts = []
    for i in range(2):
        prompt, suffix = infill_context(task, condition, previous, feedback)
        options = dict(pilot.OPTIONS)
        if i:
            options.update(temperature=0.25, seed=43)
        model_start = time.monotonic()
        response = pilot.request("generate", {
            "model": MODEL, "prompt": prompt, "suffix": suffix,
            "options": options, "stream": False, "keep_alive": "2m",
        })
        model_ms = pilot.elapsed(model_start)
        previous = response["response"]
        tool_start = time.monotonic()
        status, detail, code = materialize(tools, task, condition, previous)
        if status == "pass":
            status, detail = tools.evaluate(task, lang, code, task["public"])
        attempts.append({
            "input_tokens": response["prompt_eval_count"], "output_tokens": response["eval_count"],
            "model_ms": model_ms, "tool_ms": pilot.elapsed(tool_start),
            "load_ms": response["load_duration"] / 1e6, "prompt_eval_ms": response["prompt_eval_duration"] / 1e6,
            "generation_ms": response["eval_duration"] / 1e6, "done_reason": response.get("done_reason"),
            "public_outcome": status, "public_detail": detail, "outcome": status,
            "prompt": prompt, "suffix": suffix, "response": previous, "sampling": options,
        })
        if status == "pass":
            break
        feedback = repair_feedback(task, "python" if condition == "gpp_projected" else lang, detail)
    workflow = pilot.elapsed(start)
    accepted, oracle_ms, oracle_detail = False, 0.0, ""
    if status == "pass":
        oracle_start = time.monotonic()
        result, oracle_detail = tools.evaluate(task, lang, code, task["heldout"], heldout=True)
        oracle_ms = pilot.elapsed(oracle_start)
        accepted = result == "pass"
        attempts[-1]["outcome"] = "accepted" if accepted else "heldout_" + result
    return {
        "model": MODEL, "task": task["id"], "condition": condition, "language": lang,
        "kind": task["kind"], "form": task["form"], "seed": 42, "attempts": attempts,
        "first_accepted": accepted and len(attempts) == 1, "accepted": accepted,
        "wall_ms": workflow, "heldout_ms": oracle_ms, "heldout_detail": oracle_detail,
    }


def main():
    from replication_tasks import TASKS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    tools = Tools(pilot.ROOT, pilot.ROOT / "target/debug/gpp")
    tools.canaries()
    # Exercise the fixed edit boundary on unrelated inputs before scoring any model.
    for form, answers in [
        ("expr", {"gpp": "x + 3", "python": "x + 3", "rust": "x + 3"}),
        ("body", {"gpp": "return x + 3;", "python": "return x + 3", "rust": "return x + 3;"}),
    ]:
        probe = {"form": form, "params": [("x", "int")]}
        for condition in CONDITIONS:
            lang = condition.split("_")[0]
            raw = answers["python" if condition == "gpp_projected" else lang]
            status, detail, code = materialize(tools, probe, condition, raw)
            if status == "pass":
                status, detail = tools.evaluate(probe, lang, code, [((2,), 5), ((-5,), -2)])
            if status != "pass":
                raise ValueError(f"{condition} {form} adapter failed calibration: {detail}")
    installed = {m["name"]: m["digest"] for m in pilot.request("tags")["models"]}
    base = pilot.request("show", {"name": MODEL})["template"]
    if ".Suffix" not in base:
        raise ValueError("Model template lacks infill support.")
    # The same model's chat and FIM templates deliver genuinely different input formats.
    chat_template = ("<|im_start|>system\n{{ .System }}<|im_end|>\n"
                     "<|im_start|>user\n{{ .Prompt }}<|im_end|>\n"
                     "<|im_start|>assistant\n{{ .Response }}<|im_end|>")
    files = [*pilot.ROOT.glob("src/*"), *pilot.ROOT.glob("spec/*"),
             HERE.parent / "empirical/run.py", HERE.parent / "empirical/evaluate.py",
             pilot.ROOT / "tools/scalar_fragment.py"]
    files.extend(HERE / f for f in ("replication_tasks.py", "fragments.py", "run_study.py",
                                    "run_infill.py", "infill-protocol.md"))
    config = dict(type="metadata", study="scalar-infill-replication-v3", models=[MODEL],
                  model_digests={MODEL: installed[MODEL]}, model_template=base,
                  conditions=CONDITIONS, primary="gpp_fim", secondary="gpp_projected", order_seed=ORDER_SEED,
                  chat_template=chat_template, model_options=pilot.OPTIONS,
                  repair_options={**pilot.OPTIONS, "temperature": 0.25, "seed": 43},
                  languages=pilot.LANGUAGES, seeds=[42], max_attempts=2,
                  tasks=[t["id"] for t in TASKS], task_kinds={t["id"]: t["kind"] for t in TASKS},
                  holdout_total=sum(len(t["heldout"]) for t in TASKS),
                  public_total=sum(len(t["public"]) for t in TASKS),
                  ollama_version=pilot.request("version")["version"],
                  host=platform.platform(), python=platform.python_version(),
                  cpu=subprocess.check_output(["/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string"], text=True).strip(),
                  mypy=subprocess.check_output([tools.python, "-m", "mypy", "--version"], text=True).strip(),
                  rust=subprocess.check_output([tools.rustc, "--version"], text=True).strip(),
                  file_sha256={str(p.relative_to(pilot.ROOT)): pilot.digest(p) for p in files if p.is_file()},
                  gpp_sha256=pilot.digest(tools.gpp))
    config = json.loads(json.dumps(config))
    if args.output.exists():
        with args.output.open() as stream:
            old = json.loads(next(stream))
            if any(old.get(k) != v for k, v in config.items()):
                raise ValueError("The infill study manifest changed.")
            rows = [json.loads(line) for line in stream]
    else:
        config["validated_reference_results"] = pilot.verified_cases(tools, TASKS)
        config["started_at"] = datetime.now(timezone.utc).isoformat()
        with args.output.open("x") as stream:
            print(json.dumps(config), file=stream)
        rows = []
    complete = {(r["task"], r["condition"]) for r in rows}
    if len(complete) != len(rows):
        raise ValueError("Duplicate trial")
    rng = random.Random(ORDER_SEED)
    tasks = TASKS.copy()
    rng.shuffle(tasks)
    with args.output.open("a", buffering=1) as stream:
        for task in tasks:
            arms = list(CONDITIONS)
            rng.shuffle(arms)
            for condition in arms:
                key = task["id"], condition
                if key in complete:
                    continue
                row = trial(tools, task, condition, chat_template)
                print(json.dumps(row, ensure_ascii=False), file=stream)
                complete.add(key)
                print(f"{len(complete)}/{len(tasks) * len(arms)} {key} {row['attempts'][-1]['outcome']}", flush=True)


if __name__ == "__main__":
    main()
