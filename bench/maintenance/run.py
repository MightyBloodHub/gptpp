"""Run the frozen multi-caller maintenance experiment."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import random
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for module in (HERE.parent / "iterate", ROOT / "tools"):
    sys.path.insert(0, str(module))

from run_boundary import MODEL, STOPS
from run_study import pilot, Tools
from evaluate import arguments
from caller_context import caller_context
from evaluate_project import evaluate, functions, materialize, projection_signature, source_for

ORDER_SEED = 11839
CONDITIONS = ("gpp_context", "python_context", "rust_context", "gpp_target", "gpp_projected")
PRIMARY = "python_context"
LABELS = {
    "gpp_context": "GPT++ with caller context",
    "python_context": "Typed Python with caller context",
    "rust_context": "Rust with caller context",
    "gpp_target": "GPT++ target only",
    "gpp_projected": "GPT++ from Python syntax with caller context",
}


def workload():
    from cases_a import TASKS as a
    from cases_b import TASKS as b
    return [*a, *b]


def roster(tasks):
    rng = random.Random(ORDER_SEED)
    shuffled = tasks.copy()
    rng.shuffle(shuffled)
    for task in shuffled:
        arms = list(CONDITIONS)
        rng.shuffle(arms)
        for condition in arms:
            yield task, condition


def render(task, condition, source, previous=None, diagnostic=None):
    language = condition.split("_")[0]
    projected = condition == "gpp_projected"
    surface = "python" if projected else language
    declarations = functions(source, language)
    target = declarations[task["target"]]
    signature = projection_signature(task) if projected else target.signature
    context = [task["description"], "Edit only this function. Preserve behavior required by its callers.",
               "Public examples:"]
    for entry, args, expected in task["public"]:
        context.append(f"{entry}({arguments(args, surface)}) = {expected}")
    context.extend(["Current target:", source[target.start:target.end].rstrip()])
    if condition != "gpp_target":
        excerpts = caller_context([fn.record() for fn in declarations.values()], target.name, language)
        if excerpts:
            context.append(excerpts)
    if surface == "gpp":
        if task["form"] == "expr":
            context.append("GPT++ conditional value: if flag { yes } else { no }.")
        else:
            context.append("GPT++ uses let for constants, var for mutable locals, and semicolons for statements.")
    elif projected:
        context.append("Use scalar Python syntax. // truncates toward zero. % follows the dividend. "
                       "Use while and integer abs(x), min(x, y), max(x, y).")
    if previous is not None:
        context.extend(["Previous attempt:", previous, "Public feedback:", diagnostic, "Correct this failure."])
    if surface == "python":
        comment, prefix_end, suffix = "#", ":\n", "\n\n# End of function\n"
        signature = signature.removesuffix(":")
    else:
        comment, prefix_end = "//", " {\n"
        suffix = (";" if task["form"] == "expr" else "") + "\n}\n"
    prefix = signature + prefix_end + "    " + ("return " if task["form"] == "expr" else "")
    prompt = "".join(f"{comment} {line}\n" for paragraph in context for line in paragraph.splitlines())
    return prompt + prefix, suffix, surface


def trial(tools, task, condition, default_stops):
    started = time.monotonic()
    language = condition.split("_")[0]
    base = source_for(task, language)
    previous = diagnostic = None
    attempts = []
    for i in range(2):
        prompt, suffix, surface = render(task, condition, base, previous, diagnostic)
        options = dict(pilot.OPTIONS)
        if i:
            options.update(seed=43, temperature=0.25)
        options["stop"] = list(dict.fromkeys(default_stops + STOPS[surface]))
        call_start = time.monotonic()
        reply = pilot.request("generate", {"model": MODEL, "prompt": prompt, "suffix": suffix,
                              "options": options, "keep_alive": "3m", "stream": False})
        model_ms = pilot.elapsed(call_start)
        tool_start = time.monotonic()
        previous = reply["response"]
        status, diagnostic, patched = materialize(tools, task, language, surface, base, previous)
        stage = "patch"
        if status == "pass":
            stage = "public"
            status, diagnostic = evaluate(tools, language, patched, task["public"])
        attempts.append({
            "prompt": prompt, "suffix": suffix, "response": previous, "sampling": options,
            "input_tokens": reply.get("prompt_eval_count", 0), "output_tokens": reply.get("eval_count", 0),
            "done_reason": reply.get("done_reason"), "model_ms": model_ms,
            "tool_ms": pilot.elapsed(tool_start), "load_ms": reply.get("load_duration", 0) / 1e6,
            "generation_ms": reply.get("eval_duration", 0) / 1e6, "stage": stage,
            "public_outcome": status, "public_detail": diagnostic, "outcome": status,
            "patch_sha256": hashlib.sha256(patched.encode()).hexdigest() if patched else None,
        })
        if status == "pass":
            break
    wall_ms = pilot.elapsed(started)
    accepted, heldout_ms, heldout_detail = False, 0, ""
    if status == "pass":
        checked = time.monotonic()
        result, heldout_detail = evaluate(tools, language, patched, task["heldout"], already_checked=True)
        heldout_ms = pilot.elapsed(checked)
        accepted = result == "pass"
        attempts[-1]["outcome"] = "accepted" if accepted else "heldout_" + result
    return {
        "model": MODEL, "task": task["id"], "condition": condition, "language": language,
        "seed": 42, "kind": "maintenance", "form": task["form"], "attempts": attempts,
        "accepted": accepted, "first_accepted": accepted and len(attempts) == 1,
        "wall_ms": wall_ms, "heldout_ms": heldout_ms, "heldout_detail": heldout_detail,
    }


def calibrate(tools, tasks):
    count = 0
    for task in tasks:
        target = task["target"]
        if not task.get("source_url") or not task.get("provenance"):
            raise ValueError(f"Missing maintenance provenance for {task['id']}.")
        examples = task["public"] + task["heldout"]
        if len({(fn, tuple(args)) for fn, args, _ in examples}) != len(examples):
            raise ValueError(f"Repeated cases for {task['id']}.")
        if len({entry for entry, _, _ in task["heldout"]} - {target}) < 2:
            raise ValueError(f"Two distinct callers are required for {task['id']}.")
        old_python = source_for(task, "python")
        preserved = []
        for example in task["heldout"]:
            status, detail = evaluate(tools, "python", old_python, [example], already_checked=True)
            if status == "pass":
                preserved.append(example)
            elif status != "wrong_answer":
                raise ValueError(f"Cannot classify starter case {task['id']}: {status} {detail}")
        if len({entry for entry, _, _ in preserved} - {target}) < 2:
            raise ValueError(f"Preservation cases must cover two callers for {task['id']}.")
        for language in ("gpp", "python", "rust"):
            starter, reference = [source_for(task, language, variant) for variant in ("starter", "reference")]
            declarations = functions(starter, language)
            if declarations.keys() != functions(reference, language).keys():
                raise ValueError(f"Reference changed the function roster for {task['id']} {language}.")
            if declarations[target].signature != functions(reference, language)[target].signature:
                raise ValueError(f"Reference changed the target declaration for {task['id']} {language}.")
            for entry, _, _ in examples:
                if entry not in declarations:
                    raise ValueError(f"Unresolved test entry {entry}.")
            excerpts = caller_context([fn.record() for fn in declarations.values()], target, language)
            if not excerpts:
                raise ValueError(f"No caller excerpts selected for {task['id']} {language}.")
            status, detail = evaluate(tools, language, reference, examples)
            if status != "pass":
                raise ValueError(f"Reference {task['id']} {language}: {status} {detail}")
            status, detail = evaluate(tools, language, starter, examples)
            if status != "wrong_answer":
                raise ValueError(f"Starter {task['id']} {language}: {status} {detail}")
            status, detail = evaluate(tools, language, starter, preserved)
            if status != "pass":
                raise ValueError(f"Preservation {task['id']} {language}: {status} {detail}")
            count += len(examples)
        print(f"Calibrated {task['id']}", flush=True)
    return count


def manifest(tools, tasks):
    meta = pilot.request("show", {"name": MODEL})
    digests = {m["name"]: m["digest"] for m in pilot.request("tags")["models"]}
    if ".Suffix" not in meta["template"]:
        raise ValueError("The locked model requires native infill support.")
    defaults = [json.loads(line.split(None, 1)[1]) for line in meta.get("parameters", "").splitlines()
                if line.split(None, 1)[:1] == ["stop"]]
    files = [*ROOT.glob("src/*"), *ROOT.glob("spec/*"), *HERE.glob("cases_*.py"),
             HERE / "run.py", HERE / "evaluate_project.py", HERE / "protocol.md"]
    files.extend(ROOT / path for path in (
        "tools/caller_context.py", "tools/scalar_builtins.py", "tools/scalar_fragment.py",
        "bench/empirical/run.py", "bench/empirical/evaluate.py", "bench/iterate/run_study.py",
        "bench/iterate/fragments.py", "bench/iterate/run_boundary.py", "bench/iterate/run_infill.py"
    ))
    return {
        "type": "metadata", "study": "multi-caller-maintenance-v5",
        "models": [MODEL], "seeds": [42], "model_digests": {MODEL: digests[MODEL]},
        "model_template": meta["template"], "ollama_version": pilot.request("version")["version"],
        "host": platform.platform(), "python": platform.python_version(),
        "mypy": subprocess.check_output([tools.python, "-m", "mypy", "--version"], text=True).strip(),
        "rust": subprocess.check_output([tools.rustc, "--version"], text=True).strip(),
        "conditions": list(CONDITIONS), "primary_comparator": PRIMARY, "order_seed": ORDER_SEED,
        "model_options": pilot.OPTIONS, "default_stops": defaults, "boundary_stops": STOPS,
        "tasks": [task["id"] for task in tasks],
        "sources": {task["id"]: {"source_url": task["source_url"], "provenance": task["provenance"]} for task in tasks},
        "public_cases": sum(len(t["public"]) for t in tasks), "hidden_cases": sum(len(t["heldout"]) for t in tasks),
        "corpus_sha256": hashlib.sha256(json.dumps(tasks, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
        "file_sha256": {str(p.relative_to(ROOT)): pilot.digest(p) for p in files if p.is_file()},
        "gpp_sha256": pilot.digest(tools.gpp),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--calibrate", action="store_true")
    args = parser.parse_args()
    if not args.output and not args.calibrate:
        parser.error("provide an output path or use --calibrate")
    tasks = workload()
    if len(tasks) != 8 or len({t["id"] for t in tasks}) != 8:
        raise ValueError("The protocol calls for eight distinct task families.")
    tools = Tools(ROOT, ROOT / "target/debug/gpp")
    tools.canaries()
    if args.calibrate:
        print(f"{calibrate(tools, tasks)} reference results validated.")
        return
    settings = manifest(tools, tasks)
    if args.output.exists():
        with args.output.open() as stream:
            archived = json.loads(next(stream))
            if any(archived.get(key) != value for key, value in settings.items()):
                raise ValueError("Cannot resume with a changed manifest.")
            rows = [json.loads(line) for line in stream]
    else:
        settings["reference_cases_checked"] = calibrate(tools, tasks)
        settings["started_at"] = datetime.now(timezone.utc).isoformat()
        with args.output.open("x") as stream:
            print(json.dumps(settings), file=stream)
        rows = []
    sequence = list(roster(tasks))
    if [(r["task"], r["condition"]) for r in rows] != [
            (task["id"], condition) for task, condition in sequence[:len(rows)]]:
        raise ValueError("Run history diverges from the locked assignment.")
    with args.output.open("a", buffering=1) as stream:
        for i, (task, condition) in enumerate(sequence[len(rows):], len(rows) + 1):
            row = trial(tools, task, condition, settings["default_stops"])
            print(json.dumps(row, ensure_ascii=False), file=stream)
            print(f"{i}/{len(sequence)} {task['id']} {condition} {row['attempts'][-1]['outcome']}", flush=True)


if __name__ == "__main__":
    main()
