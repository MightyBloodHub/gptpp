"""Paired infill experiment with a model-side stop at the editable function boundary."""
import argparse
import ast
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import random
import textwrap
import time

import run_infill as fim
from run_study import HERE, Tools, pilot, repair_feedback
from fragments import edited_function
from scalar_builtins import lower_fragment

MODEL = fim.MODEL
ORDER_SEED = 7307
ARMS = ("gpp_open", "gpp_stop", "rust_open", "rust_stop", "python_open", "python_stop", "gpp_projected_stop")
STOPS = {"gpp": ["\n}"], "rust": ["\n}"],
         "python": ["\ndef ", "\nclass ", "\nimport ", "\nfrom ", "\nassert ", "\nprint(", "\nif __name__", "\n@"]}


def materialize(tools, task, arm, raw):
    lang = arm.split("_")[0]
    if arm != "gpp_projected_stop":
        return edited_function(tools, task, lang, raw)
    status, detail, code = edited_function(tools, task, "python", raw)
    if status != "pass":
        return status, detail, ""
    if task["form"] == "expr":
        fragment = ast.unparse(ast.parse(code).body[0].body[0].value)
    else:
        fragment = textwrap.dedent(code.split("\n", 1)[1]).strip()
    try:
        draft = lower_fragment(fragment, task["form"], task["params"])
    except ValueError as exc:
        return "check_error", str(exc)[:600], ""
    return edited_function(tools, task, "gpp", draft)


def trial(tools, task, arm, default_stops):
    projected = arm == "gpp_projected_stop"
    lang = arm.split("_")[0]
    surface = "python" if projected else lang
    template_arm = "gpp_projected" if projected else lang + "_fim"
    before = time.monotonic()
    previous = feedback = None
    attempts = []
    for i in range(2):
        prompt, suffix = fim.infill_context(task, template_arm, previous, feedback)
        sampling = dict(pilot.OPTIONS)
        if i:
            sampling.update(seed=43, temperature=0.25)
        if arm.endswith("_stop"):
            sampling["stop"] = list(dict.fromkeys(default_stops + STOPS[surface]))
        call = time.monotonic()
        reply = pilot.request("generate", {"model": MODEL, "prompt": prompt, "suffix": suffix,
                             "options": sampling, "keep_alive": "2m", "stream": False})
        model_ms = pilot.elapsed(call)
        previous = reply["response"]
        check = time.monotonic()
        status, detail, code = materialize(tools, task, arm, previous)
        if status == "pass":
            status, detail = tools.evaluate(task, lang, code, task["public"])
        attempts.append({"prompt": prompt, "suffix": suffix, "response": previous, "sampling": sampling,
                         "model_ms": model_ms, "tool_ms": pilot.elapsed(check),
                         "load_ms": reply["load_duration"] / 1e6, "generation_ms": reply["eval_duration"] / 1e6,
                         "prompt_eval_ms": reply["prompt_eval_duration"] / 1e6, "done_reason": reply["done_reason"],
                         "public_outcome": status, "public_detail": detail, "outcome": status,
                         "input_tokens": reply["prompt_eval_count"], "output_tokens": reply["eval_count"]})
        if status == "pass":
            break
        feedback = repair_feedback(task, surface, detail)
    wall_ms = pilot.elapsed(before)
    oracle_ms, oracle_detail, accepted = 0, "", False
    if status == "pass":
        check = time.monotonic()
        verdict, oracle_detail = tools.evaluate(task, lang, code, task["heldout"], heldout=True)
        oracle_ms = pilot.elapsed(check)
        accepted = verdict == "pass"
        attempts[-1]["outcome"] = "accepted" if accepted else "heldout_" + verdict
    return {"model": MODEL, "task": task["id"], "kind": task["kind"], "form": task["form"], "language": lang,
            "condition": arm, "seed": 42, "attempts": attempts, "accepted": accepted,
            "first_accepted": accepted and len(attempts) == 1, "wall_ms": wall_ms,
            "heldout_ms": oracle_ms, "heldout_detail": oracle_detail}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    from boundary_tasks import TASKS
    tools = Tools(pilot.ROOT, pilot.ROOT / "target/debug/gpp")
    tools.canaries()
    model = pilot.request("show", {"name": MODEL})
    installed = {m["name"]: m["digest"] for m in pilot.request("tags")["models"]}
    # Ollama renders installed stop parameters as 'stop <JSON-quoted string>'.
    stops = [json.loads(line.split(None, 1)[1]) for line in model.get("parameters", "").splitlines()
             if line.strip().split(None, 1)[:1] == ["stop"]]
    if ".Suffix" not in model["template"]:
        raise ValueError("The installed template lacks native infill.")
    files = [*pilot.ROOT.glob("src/*"), *pilot.ROOT.glob("spec/*"),
             HERE.parent / "empirical/run.py", HERE.parent / "empirical/evaluate.py",
             pilot.ROOT / "tools/scalar_fragment.py", pilot.ROOT / "tools/scalar_builtins.py"]
    files.extend(HERE / f for f in ("tasks.py", "boundary_tasks.py", "fragments.py", "run_study.py",
                                    "run_infill.py", "run_boundary.py", "boundary-protocol.md"))
    meta = {"type": "metadata", "study": "scalar-boundary-stop-v4", "models": [MODEL], "seeds": [42],
            "model_digests": {MODEL: installed[MODEL]}, "ollama_version": pilot.request("version")["version"],
            "model_template": model["template"], "default_stops": stops, "boundary_stops": STOPS,
            "model_options": pilot.OPTIONS, "repair_options": {**pilot.OPTIONS, "seed": 43, "temperature": 0.25},
            "max_attempts": 2, "conditions": list(ARMS), "order_seed": ORDER_SEED,
            "tasks": [t["id"] for t in TASKS], "task_kinds": {t["id"]: t["kind"] for t in TASKS},
            "public_total": sum(len(t["public"]) for t in TASKS), "holdout_total": sum(len(t["heldout"]) for t in TASKS),
            "corpus_sha256": sha256(json.dumps(TASKS, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
            "gpp_sha256": pilot.digest(tools.gpp), "file_sha256":
            {str(p.relative_to(pilot.ROOT)): pilot.digest(p) for p in files if p.is_file()}}
    if args.output.exists():
        with args.output.open() as stream:
            archived = json.loads(next(stream))
            if any(archived.get(k) != v for k, v in meta.items()):
                raise ValueError("Cannot resume a changed manifest.")
            rows = [json.loads(line) for line in stream]
    else:
        meta["validated_reference_results"] = pilot.verified_cases(tools, TASKS)
        meta["started_at"] = datetime.now(timezone.utc).isoformat()
        with args.output.open("x") as stream:
            print(json.dumps(meta), file=stream)
        rows = []
    rng = random.Random(ORDER_SEED)
    tasks = TASKS.copy()
    rng.shuffle(tasks)
    roster = []
    for t in tasks:
        arms = list(ARMS)
        rng.shuffle(arms)
        roster.extend((t, arm) for arm in arms)
    if [(r["task"], r["condition"]) for r in rows] != [(t["id"], a) for t, a in roster[:len(rows)]]:
        raise ValueError("Existing trials differ from the assigned order.")
    with args.output.open("a", buffering=1) as stream:
        for i, (t, arm) in enumerate(roster[len(rows):], len(rows) + 1):
            row = trial(tools, t, arm, stops)
            print(json.dumps(row, ensure_ascii=False), file=stream)
            print(f"{i}/{len(roster)} {t['id']} {arm} {row['attempts'][-1]['outcome']}", flush=True)


if __name__ == "__main__":
    main()
