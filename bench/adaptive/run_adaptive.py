"""Measure caller context triggered by a failed public test on fresh projects."""

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import random
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
MAINTENANCE = HERE.parent / "maintenance"
sys.path.insert(0, str(ROOT))
sys.path.append(str(MAINTENANCE))

# The previous maintenance runner and its transitive scalar runner both use
# run.py. Load the previous runner under a separate module name.
spec = importlib.util.spec_from_file_location("prior_maintenance", MAINTENANCE / "run.py")
maintenance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(maintenance)

from evaluate import arguments
from evaluate_project import evaluate, materialize, source_for

ORDER_SEED = 12713
STUDY = "multi-caller-adaptive-v6"
CONDITIONS = ("gpp_adaptive", "python_adaptive", "rust_adaptive", "gpp_target", "gpp_context")
PRIMARY = "python_adaptive"
MODEL = maintenance.MODEL
STOPS = maintenance.STOPS
pilot = maintenance.pilot
Tools = maintenance.Tools


def workload():
    from bench.adaptive.cases_a import TASKS as group_a
    from bench.adaptive.cases_b import TASKS as group_b
    return [*group_a, *group_b]


def roster(tasks):
    rng = random.Random(ORDER_SEED)
    tasks = tasks.copy()
    rng.shuffle(tasks)
    for task in tasks:
        conditions = list(CONDITIONS)
        rng.shuffle(conditions)
        yield from ((task, condition) for condition in conditions)


def render(task, language, source, include_callers, previous=None, diagnostic=None):
    declarations = maintenance.functions(source, language)
    target = declarations[task["target"]]
    context = [task["description"], "Edit only this function. Preserve behavior required by its callers.",
               "Public examples:"]
    context.extend(f"{name}({arguments(args, language)}) = {expected}"
                   for name, args, expected in task["public"])
    context.extend(["Current target:", source[target.start:target.end].rstrip()])
    if include_callers:
        excerpts = maintenance.caller_context([fn.record() for fn in declarations.values()],
                                              target.name, language)
        if excerpts:
            context.append(excerpts)
    if language == "gpp":
        hint = ("GPT++ conditional value: if flag { yes } else { no }." if task["form"] == "expr"
                else "GPT++ uses let for constants, var for mutable locals, and semicolons for statements.")
        context.append(hint)
    if previous is not None:
        context.extend(["Previous attempt:", previous, "Public feedback:", diagnostic, "Correct this failure."])
    if language == "python":
        comment, delimiter, suffix = "#", "\n", "\n\n# End of function\n"
    else:
        comment, delimiter = "//", " {\n"
        suffix = (";" if task["form"] == "expr" else "") + "\n}\n"
    prefix = target.signature + delimiter + "    " + ("return " if task["form"] == "expr" else "")
    prompt = "".join(f"{comment} {line}\n" for paragraph in context for line in paragraph.splitlines())
    return prompt + prefix, suffix, language


def use_callers(condition, target, failed_entry):
    return condition == "gpp_context" or (
        condition.endswith("_adaptive") and failed_entry is not None and failed_entry != target
    )


def public_evaluate(tools, language, source, cases):
    outcome, diagnostic = evaluate(tools, language, source, cases)
    if outcome in ("pass", "check_error"):
        return outcome, diagnostic, None
    if outcome == "wrong_answer":
        for name, args, _ in cases:
            call = f"{name}({arguments(args, language)})"
            if diagnostic.startswith(call + " returned "):
                return outcome, diagnostic, name
    # A later runtime fault may have prevented the batch from reaching output
    # comparison, so evaluate the supplied cases in order to locate the first
    # failure. MyPy has already checked the same patch.
    for case in cases:
        status, detail = evaluate(tools, language, source, [case], already_checked=True)
        if status == "check_error":
            return status, detail, None
        if status != "pass":
            name, args, _ = case
            if status == "runtime_error":
                detail = f"{name}({arguments(args, language)}) failed during execution. {detail}"
            return status, detail[:600], name
    return outcome, diagnostic, None


def trial(tools, task, condition, default_stops):
    started = time.monotonic()
    language = condition.split("_")[0]
    source = source_for(task, language)
    previous = diagnostic = failed_entry = None
    attempts = []
    for index in range(2):
        included = use_callers(condition, task["target"], failed_entry)
        prompt, suffix, surface = render(task, language, source, included, previous, diagnostic)
        settings = {**pilot.OPTIONS, "stop": list(dict.fromkeys(default_stops + STOPS[surface]))}
        if index:
            settings.update(seed=43, temperature=0.25)
        call_started = time.monotonic()
        reply = pilot.request("generate", {"model": MODEL, "prompt": prompt, "suffix": suffix,
                              "options": settings, "keep_alive": "3m", "stream": False})
        model_ms = pilot.elapsed(call_started)
        tool_started = time.monotonic()
        previous = reply["response"]
        outcome, diagnostic, patched = materialize(tools, task, language, surface, source, previous)
        stage, failed_entry = "patch", None
        if outcome == "pass":
            stage = "public"
            outcome, diagnostic, failed_entry = public_evaluate(tools, language, patched, task["public"])
        attempts.append({
            "prompt": prompt, "suffix": suffix, "response": previous, "sampling": settings,
            "input_tokens": reply["prompt_eval_count"], "output_tokens": reply.get("eval_count", 0),
            "done_reason": reply.get("done_reason"), "model_ms": model_ms,
            "tool_ms": pilot.elapsed(tool_started), "load_ms": reply.get("load_duration", 0) / 1e6,
            "generation_ms": reply.get("eval_duration", 0) / 1e6, "stage": stage,
            "caller_context": included, "public_failed_entry": failed_entry,
            "public_outcome": outcome, "public_detail": diagnostic, "outcome": outcome,
            "patch_sha256": sha256(patched.encode()).hexdigest() if patched else None,
        })
        if outcome == "pass":
            break
    wall_ms = pilot.elapsed(started)
    accepted, heldout_ms, heldout_detail = False, 0, ""
    if outcome == "pass":
        checked = time.monotonic()
        status, heldout_detail = evaluate(tools, language, patched, task["heldout"], already_checked=True)
        heldout_ms = pilot.elapsed(checked)
        accepted = status == "pass"
        attempts[-1]["outcome"] = "accepted" if accepted else "heldout_" + status
    return {
        "model": MODEL, "task": task["id"], "target": task["target"], "condition": condition,
        "language": language, "seed": 42, "kind": "maintenance", "form": task["form"],
        "attempts": attempts, "accepted": accepted, "first_accepted": accepted and len(attempts) == 1,
        "wall_ms": wall_ms, "heldout_ms": heldout_ms, "heldout_detail": heldout_detail,
    }


def manifest(tools, tasks):
    original = maintenance.manifest(tools, tasks)
    original.update(study=STUDY, conditions=list(CONDITIONS), primary_comparator=PRIMARY,
                    order_seed=ORDER_SEED, targets={task["id"]: task["target"] for task in tasks},
                    retry_options={**pilot.OPTIONS, "seed": 43, "temperature": 0.25})
    for path in [*HERE.glob("cases_*.py"), HERE / "run_adaptive.py", HERE / "protocol.md"]:
        original["file_sha256"][str(path.relative_to(ROOT))] = pilot.digest(path)
    return original


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
    sequence = list(roster(tasks))
    tools = Tools(ROOT, ROOT / "target/debug/gpp")
    tools.canaries()
    if args.calibrate:
        print(f"{maintenance.calibrate(tools, tasks)} reference results validated.")
        return
    settings = manifest(tools, tasks)
    if args.output.exists():
        with args.output.open() as stream:
            archived = json.loads(next(stream))
            if any(archived.get(key) != value for key, value in settings.items()):
                raise ValueError("Cannot resume with a changed manifest.")
            rows = [json.loads(line) for line in stream]
    else:
        settings["reference_cases_checked"] = maintenance.calibrate(tools, tasks)
        settings["started_at"] = datetime.now(timezone.utc).isoformat()
        with args.output.open("x") as stream:
            print(json.dumps(settings), file=stream)
        rows = []
    if [(row["task"], row["condition"]) for row in rows] != [
            (task["id"], condition) for task, condition in sequence[:len(rows)]]:
        raise ValueError("Run history diverges from the locked assignment.")
    with args.output.open("a", buffering=1) as stream:
        for index, (task, condition) in enumerate(sequence[len(rows):], len(rows) + 1):
            row = trial(tools, task, condition, settings["default_stops"])
            print(json.dumps(row, ensure_ascii=False), file=stream)
            print(f"{index}/{len(sequence)} {task['id']} {condition} {row['attempts'][-1]['outcome']}", flush=True)


if __name__ == "__main__":
    main()
