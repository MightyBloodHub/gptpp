"""Run the paired ordered-rule and protected-body maintenance study."""
import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import random
import sys
from textwrap import dedent, indent
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent / "adaptive"))
import run_adaptive as previous
from evaluate import arguments
from evaluate_project import evaluate, functions, materialize, source_for
from policy_ir import lower_policy

maintenance, pilot, Tools = previous.maintenance, previous.pilot, previous.Tools
MODELS = (previous.MODEL, "starcoder2:3b")
ARMS = ("gpp_rules", "gpp_guard", "gpp_full", "python_guard", "python_full", "rust_guard", "rust_full")
ORDER_SEED = 18591
RULE_STOPS = ["\nelse", "\n#", "```"]
STAR_STOPS = ["<file_sep>", "<fim_prefix>", "<fim_suffix>", "<fim_middle>", "<|endoftext|>"]
STUDY = "multi-caller-policy-v7"


def roster(tasks):
    for model in MODELS:
        rng = random.Random(ORDER_SEED)
        ordered = tasks.copy()
        rng.shuffle(ordered)
        for task in ordered:
            arms = list(ARMS)
            rng.shuffle(arms)
            for arm in arms:
                yield model, task, arm


def render(task, arm, source, failure=None):
    lang, mode = arm.split("_")
    decls = functions(source, lang)
    target = decls[task["target"]]
    marker = "#" if lang == "python" or mode == "rules" else "//"
    context = [task["description"], "Examples"]
    context.extend(f"{fn}({arguments(args, lang)}) = {expected}" for fn, args, expected in task["public"])
    if failure:
        response, detail = failure
        context.extend(["Previous insertion", response, detail, maintenance.caller_context(
            [fn.record() for fn in decls.values()], target.name, lang)])
    old = dedent(target.body).strip()
    if mode == "rules":
        context.extend([target.signature, "Current body", old,
                        "Write one row per changed case: when <condition> => <value>. First match wins.",
                        "Use Python expressions: True, False, and, or, not, //, min, max, abs. The final else runs the current body."])
        prefix, suffix = "when ", "\nelse => @keep\n"
    else:
        if mode == "full":
            context.extend(["Replace the current body", old])
        else:
            context.append("Insert early returns for changed cases above the existing body.")
        if lang == "gpp":
            context.append("GPT++ uses if flag { return value; }, let for constants and var for mutable locals.")
        prefix = target.signature + ("\n" if lang == "python" else " {\n") + "    "
        end = "\n\n# End of function\n" if lang == "python" else "\n}\n"
        suffix = ("\n" + indent(old, "    ") if mode == "guard" else "") + end
    comments = "".join(f"{marker} {line}\n" for part in context for line in part.splitlines())
    return comments + prefix, suffix


def generate(model, arm, prompt, suffix, defaults, retry=False):
    lang, mode = arm.split("_")
    stops = RULE_STOPS if mode == "rules" else previous.STOPS[lang]
    options = dict(pilot.OPTIONS)
    if retry:
        options.update(seed=43, temperature=0.25)
    options["stop"] = list(dict.fromkeys(defaults + (STAR_STOPS if model == MODELS[1] else []) + stops))
    payload = {"model": model, "stream": False, "keep_alive": "3m", "options": options}
    if model == MODELS[1]:
        payload.update(raw=True, prompt=f"<fim_prefix>{prompt}<fim_suffix>{suffix}<fim_middle>")
    else:
        payload.update(prompt=prompt, suffix=suffix)
    return pilot.request("generate", payload), options


def patch(tools, task, arm, source, raw):
    lang, mode = arm.split("_")
    body = raw
    old = functions(source, lang)[task["target"]].body
    if mode == "rules":
        try:
            body = lower_policy("when " + raw.rstrip() + "\nelse => @keep", task["params"], original_body=old)
        except ValueError as exc:
            return "check_error", str(exc), ""
    elif mode == "guard":
        # The original body is outside the editable range in every guard arm.
        # Its initial indentation is already part of the native Python function.
        body = raw.rstrip() + "\n" + indent(dedent(old).strip(), "    ")
    return materialize(tools, dict(task, form="body"), lang, lang, source, body)


def trial(tools, task, arm, model, defaults):
    lang = arm.split("_")[0]
    source = source_for(task, lang)
    attempts, failure = [], None
    start = time.monotonic()
    hidden_ms, hidden_detail = 0, ""
    for index in range(2):
        prompt, suffix = render(task, arm, source, failure)
        began = time.monotonic()
        reply, opts = generate(model, arm, prompt, suffix, defaults, bool(index))
        model_ms = pilot.elapsed(began)
        began = time.monotonic()
        raw = reply["response"]
        status, detail, full = patch(tools, task, arm, source, raw)
        entry, stage = None, "patch"
        if status == "pass":
            stage = "public"
            status, detail, entry = previous.public_evaluate(tools, lang, full, task["public"])
        record = dict(prompt=prompt, suffix=suffix, response=raw, sampling=opts, stage=stage,
                      caller_context=bool(index), public_failed_entry=entry, public_outcome=status,
                      public_detail=detail, outcome=status, patch_sha256=sha256(full.encode()).hexdigest() if full else None,
                      model_ms=model_ms, tool_ms=pilot.elapsed(began), done_reason=reply["done_reason"],
                      input_tokens=reply["prompt_eval_count"], output_tokens=reply["eval_count"],
                      load_ms=reply.get("load_duration", 0)/1e6, generation_ms=reply.get("eval_duration", 0)/1e6)
        attempts.append(record)
        if status == "pass":
            began = time.monotonic()
            hidden_status, hidden_detail = evaluate(tools, lang, full, task["heldout"], already_checked=True)
            hidden_ms = pilot.elapsed(began)
            record["outcome"] = "accepted" if hidden_status == "pass" else "heldout_" + hidden_status
            break
        if not entry or entry == task["target"]:
            break
        failure = raw, detail
    accepted = attempts[-1]["outcome"] == "accepted"
    return dict(task=task["id"], model=model, seed=42, condition=arm, language=lang, kind="maintenance",
                form="body", accepted=accepted, first_accepted=accepted and len(attempts)==1, attempts=attempts,
                wall_ms=pilot.elapsed(start)-hidden_ms, heldout_ms=hidden_ms, heldout_detail=hidden_detail)


def manifest(tools, tasks):
    info = maintenance.manifest(tools, tasks)
    tags = {m["name"]: m["digest"] for m in pilot.request("tags")["models"]}
    second = pilot.request("show", {"name": MODELS[1]})
    stops = [json.loads(line.split(None, 1)[1]) for line in second.get("parameters", "").splitlines()
             if line.split(None, 1)[:1] == ["stop"]]
    for path in (HERE/"run_policy.py", HERE/"fresh.py", HERE/"protocol.md", ROOT/"tools/policy_ir.py",
                 HERE.parent/"adaptive/run_adaptive.py"):
        info["file_sha256"][str(path.relative_to(ROOT))] = pilot.digest(path)
    info.update(study=STUDY, models=list(MODELS), model_digests={m: tags[m] for m in MODELS},
                model_default_stops={MODELS[0]: info["default_stops"], MODELS[1]: stops},
                star_template=second["template"], star_transport="raw-prefix-suffix-middle",
                star_stops=STAR_STOPS, rule_stops=RULE_STOPS, order_seed=ORDER_SEED,
                conditions=list(ARMS), primary="gpp_rules", primary_comparator="python_guard")
    return info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    from fresh import TASKS
    if len(TASKS) != 8 or len({t["id"] for t in TASKS}) != 8:
        raise ValueError("Expected eight distinct tasks")
    tools = Tools(ROOT, ROOT / "target/debug/gpp")
    tools.canaries()
    info = manifest(tools, TASKS)
    order = list(roster(TASKS))
    if args.output.exists():
        with args.output.open() as stream:
            old = json.loads(next(stream))
            if any(old.get(k) != v for k, v in info.items()):
                raise ValueError("Manifest changed since the first call")
            rows = [json.loads(line) for line in stream]
    else:
        info["reference_cases_checked"] = maintenance.calibrate(tools, TASKS)
        info["started_at"] = datetime.now(timezone.utc).isoformat()
        with args.output.open("x") as stream:
            print(json.dumps(info), file=stream)
        rows = []
    if [(r["model"], r["task"], r["condition"]) for r in rows] != [
        (m,t["id"],a) for m,t,a in order[:len(rows)]
    ]:
        raise ValueError("Unexpected assignment order in log")
    with args.output.open("a", buffering=1) as stream:
        for i, (model, task, arm) in enumerate(order[len(rows):], len(rows)+1):
            row = trial(tools, task, arm, model, info["model_default_stops"][model])
            print(json.dumps(row, ensure_ascii=False), file=stream)
            print(f'{i}/{len(order)} {model} {task["id"]} {arm} {row["attempts"][-1]["outcome"]}', flush=True)


if __name__ == "__main__":
    main()
