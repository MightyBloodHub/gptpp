"""Run a matched experiment on compiler-owned function fragments."""

import argparse
import json
from pathlib import Path
import random
import sys
import time
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "empirical"))
import run as pilot
from evaluate import Tools, arguments
from fragments import edited_function, old_fragment, prefix


CONDITIONS = ("gpp_full", "gpp_fragment", "python_fragment", "rust_fragment")
ORDER_SEED = 11927
SYSTEM = "Complete the supplied code. End the code block with a closing fence."
FENCE = chr(96) * 3
GUIDES = {
    "gpp": {
        "expr": "I64 expression. Conditional: if flag { x } else { y }.",
        "body": "GPT++ statements: var i = 0; while i < n { i += 1; } return i; Use let for constants.",
    },
    "python": {"expr": "Python integer expression.", "body": "Python statements."},
    "rust": {"expr": "Rust i64 expression.", "body": "Rust statements."},
}


def prompt_for(task, lang):
    examples = ", ".join(f"({arguments(args, lang)}) gives {v}" for args, v in task["public"])
    parts = [task["description"], f"Examples: {examples}."]
    old = old_fragment(task, lang)
    if old:
        parts.append("Current implementation:\n" + old)
    parts.append(GUIDES[lang][task["form"]] + " Complete the function for the full input range.")
    return "\n".join(parts)


def repair_feedback(task, lang, message):
    for args, _ in task["public"]:
        if message.startswith(f"solve{args} returned "):
            bindings = ", ".join(
                f"{param}={value}" for (param, _), value in zip(task["params"], args)
            )
            return message.replace(f"solve{args}", f"With {bindings}, the function", 1)
    if lang == "gpp":
        if "unexpected character '['" in message or "found '.'" in message:
            return message + " Only I64 and Bool are available. I64 operations include + - * / %."
        if "expected an expression, found 'let'" in message:
            return message + " An if expression takes one value in each arm, e.g. if b { x + 1 } else { x }."
        if "immutable" in message:
            return message + " Parameters and let bindings are immutable. Use var for an updated local."
    return message


def completion_template(base, lang, start):
    # The assistant turn already contains the immutable declaration. The model
    # continues inside it and naturally closes the fenced source sample.
    header = FENCE + {"gpp": "gpp", "rust": "rust", "python": "python"}[lang] + "\n" + start
    if "{{ .Response }}" in base:
        return base.replace("{{ .Response }}", header + "{{ .Response }}", 1)
    return base + header + "{{ .Response }}"


def fragment_trial(tools, model, task, lang, base_template, options=None):
    options = options or pilot.OPTIONS
    start_time = time.monotonic()
    original = prompt_for(task, lang)
    prompt = original
    start = prefix(task, lang)
    template = completion_template(base_template, lang, start)
    attempts = []
    for attempt_index in range(2):
        model_start = time.monotonic()
        call_options = dict(options)
        if attempt_index:
            call_options.update(temperature=0.25, seed=options["seed"] + 1)
        reply = pilot.request("generate", {
            "model": model, "prompt": prompt, "system": SYSTEM,
            "template": template, "stream": False, "keep_alive": "2m",
            "options": {**call_options, "stop": [FENCE, "<|eot_id|>", "<｜end▁of▁sentence｜>"]},
        })
        model_ms = pilot.elapsed(model_start)
        tool_start = time.monotonic()
        raw = reply["response"]
        status, feedback, code = edited_function(tools, task, lang, raw)
        if status == "pass":
            status, feedback = tools.evaluate(task, lang, code, task["public"])
        attempts.append({
            "prompt": prompt, "assistant_prefix": start, "response": raw,
            "input_tokens": reply["prompt_eval_count"], "output_tokens": reply["eval_count"],
            "model_ms": model_ms, "tool_ms": pilot.elapsed(tool_start),
            "load_ms": reply["load_duration"] / 1e6,
            "prompt_eval_ms": reply["prompt_eval_duration"] / 1e6,
            "generation_ms": reply["eval_duration"] / 1e6,
            "public_outcome": status, "public_detail": feedback, "sampling": call_options,
            "outcome": status, "done_reason": reply.get("done_reason"),
        })
        if status == "pass":
            break
        prompt = (original + "\nPrevious completion:\n" + raw + "\nFeedback: "
                  + repair_feedback(task, lang, feedback)
                  + "\nChange the failed calculation or syntax and complete the function again.")
    workflow = pilot.elapsed(start_time)
    accepted = False
    oracle_ms = 0
    detail = ""
    if status == "pass":
        oracle_start = time.monotonic()
        outcome, detail = tools.evaluate(task, lang, code, task["heldout"], heldout=True)
        oracle_ms = pilot.elapsed(oracle_start)
        accepted = outcome == "pass"
        attempts[-1]["outcome"] = "accepted" if accepted else "heldout_" + outcome
    return {
        "model": model, "task": task["id"], "kind": task["kind"], "form": task["form"],
        "condition": lang + "_fragment", "language": lang, "seed": pilot.SEED,
        "accepted": accepted, "first_accepted": len(attempts) == 1 and accepted, "attempts": attempts,
        "wall_ms": workflow, "heldout_ms": oracle_ms, "heldout_detail": detail,
    }


def metadata(tools, tasks, templates):
    meta = pilot.configuration(tools, tasks)
    meta.update(study="scalar-fragment-pilot-v2", conditions=list(CONDITIONS),
                order_seed=ORDER_SEED, assistant_prefill=True, fragment_system=SYSTEM,
                base_templates=templates, fragment_guides=GUIDES)
    for filename in ("tasks.py", "fragments.py", "run_study.py", "protocol.md"):
        path = HERE / filename
        meta["file_sha256"][str(path.relative_to(pilot.ROOT))] = pilot.digest(path)
    return json.loads(json.dumps(meta))


def main():
    from tasks import TASKS
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    tools = Tools(pilot.ROOT, pilot.ROOT / "target/debug/gpp")
    tools.canaries()
    templates = {m: pilot.request("show", {"name": m})["template"] for m in pilot.MODELS}
    manifest = metadata(tools, TASKS, templates)
    if args.output.exists():
        with args.output.open() as stream:
            old = json.loads(next(stream))
            if any(old.get(k) != v for k, v in manifest.items()):
                raise RuntimeError("The run manifest changed. Use a fresh output path.")
            rows = [json.loads(line) for line in stream]
    else:
        manifest["validated_reference_results"] = pilot.verified_cases(tools, TASKS)
        manifest["started_at"] = datetime.now(timezone.utc).isoformat()
        with args.output.open("x") as stream:
            print(json.dumps(manifest), file=stream)
        rows = []
    complete = {(r["model"], r["task"], r["condition"]) for r in rows}
    if len(complete) != len(rows):
        raise RuntimeError("Duplicate trial")
    rng = random.Random(ORDER_SEED)
    total = len(TASKS) * len(pilot.MODELS) * len(CONDITIONS)
    with args.output.open("a", buffering=1) as stream:
        for model in pilot.MODELS:
            tasks = TASKS.copy()
            rng.shuffle(tasks)
            for task in tasks:
                conditions = list(CONDITIONS)
                rng.shuffle(conditions)
                for condition in conditions:
                    key = model, task["id"], condition
                    if key in complete:
                        continue
                    if condition == "gpp_full":
                        row = pilot.trial(tools, model, task, "gpp")
                        row.update(condition=condition, form=task["form"])
                    else:
                        lang = condition.split("_")[0]
                        row = fragment_trial(tools, model, task, lang, templates[model])
                    print(json.dumps(row, ensure_ascii=False), file=stream)
                    complete.add(key)
                    print(f"{len(complete)}/{total} {key} {row['attempts'][-1]['outcome']}", flush=True)


if __name__ == "__main__":
    main()
