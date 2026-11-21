"""One frozen paired experiment. This collector receives only public assignments."""

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import platform
import random
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import monotonic

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import acceptance
from propose import ollama
from public import TASKS, literal, obligation, points, public_answer, signature, sketch
import native_controls as native

MODEL = "qwen2.5-coder:7b"
MODEL_DIGEST = "dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364"
ARMS = ("direct", "direct_retry", "direct_witness", "search", "workflow")
LANGUAGES = ("gpp", "python", "rust")
BINARY = ROOT / "target/release/gpp"
LIMIT = 256
BUDGET = 10000
MANIFEST = HERE / "freeze.json"


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def utc():
    return datetime.now(timezone.utc).isoformat()


def verify_freeze():
    freeze = json.loads(MANIFEST.read_text())
    for file, value in freeze["sources"].items():
        if digest(ROOT / file) != value:
            raise ValueError(f"Frozen source changed: {file}")
    return freeze


def emit(store, row):
    print(json.dumps(row, separators=(",", ":"), allow_nan=False), file=store, flush=True)


def ordered_inputs(task, inputs):
    values = tuple(inputs[name] for name, _ in task.args)
    if any(type(v) is not type(lo) or not lo <= v <= hi
           for v, (lo, hi) in zip(values, task.bounds, strict=True)):
        raise LookupError("Outside the public reference's authorized input domain")
    return values


def edit_site(task, lang):
    types = {"rust": {"I64": "i64", "Bool": "bool"}, "python": {"I64": "int", "Bool": "bool"}}
    if lang == "gpp":
        return f"fn update({signature(task)}) -> {task.result}"
    ts = types[lang]
    args = ", ".join(f"{name}: {ts[ty]}" for name, ty in task.args)
    return f"{'def' if lang == 'python' else 'fn'} update({args}) -> {ts[task.result]}"


def portable_check(lang, task, expression, source, work):
    start = monotonic()
    contract = obligation(task)
    rule = dict(**contract, domain=dict(zip((n for n, _ in task.args), task.bounds)), status="not_run")
    site = dict(function="update", type=task.result, signature=edit_site(task, lang), previous=expression)
    row = dict(source=source, expression=expression, edit_site=site, obligations=[rule], feedback=None,
               decision="abstain", public_examples={"status": "not_run", "contracts": []})
    examples = task.examples
    domain = list(points(task))
    try:
        xs = [x for x, _ in examples] + domain
        outcomes = native.observe(lang, task, expression, xs, work)
        if len(xs) != len(outcomes):
            raise RuntimeError("Native observer returned an incomplete batch")
        values = iter(outcomes)
        groups = (("sample", examples), ("accept_edit", [(x, public_answer(task, x)) for x in domain]))
        for group, checks in groups:
            target = row["public_examples"] if group == "sample" else rule
            for i, (x, expect) in enumerate(checks):
                actual = next(values)
                matches = type(actual) is type(expect) and actual == expect
                name = f"sample_{i}" if group == "sample" else group
                status = "passed" if matches else "counterexample"
                target.update(status=status, checked=i + 1)
                if group == "sample":
                    target["contracts"].append(dict(name=name, status=status))
                if not matches:
                    names = dict(zip((n for n, _ in task.args), x))
                    result = {"value": actual} if actual is not None else {"fault": "arithmetic_fault"}
                    feedback = dict(contract=name, rule=task.request, inputs=names, args=x, edit_site=site,
                                    observed=[dict(locals=names, **result)], contract_result={"result": False})
                    target["counterexample"] = dict(inputs=names, expected=expect, observed=actual)
                    row.update(decision="reject", reason="public_example" if group == "sample" else "contract_counterexample",
                               feedback=feedback)
                    return row
        row.update(decision="accept", reason="declared_contracts_discharged")
    except native.CandidateError as exc:
        row.update(decision="reject", reason="invalid_expression", feedback=dict(edit_site=site, diagnostic=str(exc)))
    except subprocess.TimeoutExpired:
        row.update(reason="tool_timeout")
    finally:
        row["tool_seconds"] = monotonic() - start
    return row


def compact_feedback(task, feedback):
    """Identical semantic fields across languages; strip backend-specific source spans and harness logs."""
    if "diagnostic" in feedback:
        return "The previous expression did not parse or type-check in the specified edit site."
    observed = feedback["observed"]
    if not observed:
        raise ValueError("Missing replay observation")
    observation = observed[0]
    inputs = {n: observation["locals"][n] for n, _ in task.args}
    actual = observation.get("value", observation.get("fault"))
    if feedback["contract"].startswith("sample_"):
        _, expected = task.examples[int(feedback["contract"].removeprefix("sample_"))]
        rule = f"This public example requires {literal(expected)}."
    else:
        rule = task.request
    return json.dumps(dict(input=inputs, observed=actual, violated_rule=rule), separators=(",", ":"))


def request(task, lang, previous=None, feedback=None):
    args = dict(model=MODEL, stream=False, keep_alive="5m",
                format={"type": "object", "properties": {"expression": {"type": "string"}},
                        "required": ["expression"], "additionalProperties": False},
                options=dict(temperature=0, seed=42 if previous is None else 43, num_predict=180, num_ctx=4096))
    name = {"gpp": "GPT++", "rust": "Rust", "python": "typed Python"}[lang]
    lines = [f"Change the single return expression of this {name} function.", edit_site(task, lang),
             "Old expression: " + native.translate(task.previous, lang), task.request,
             "Public contract bounds (inclusive): " + str(dict(zip((n for n, _ in task.args), task.bounds))),
             "Public examples: " + json.dumps(task.examples, separators=(",", ":")), native.syntax_guide(lang),
             'Return {"expression":"one native scalar expression"}. No statements or explanation.']
    if previous is not None:
        lines.extend(["The previous proposed expression failed a public check:", previous,
                      feedback or "Review the requested behavior and try once more."])
    args["prompt"] = "\n".join(lines)
    return args


def metered_reply(port, req, assignment, store, start):
    try:
        reply = ollama(port, "generate", req)
        if reply.get("done") is not True or any(
                type(reply.get(k)) is not int for k in ("prompt_eval_count", "eval_count")):
            raise RuntimeError("Incomplete Ollama usage receipt")
        return reply
    except Exception as exc:
        # Preserve the incomplete physical call. A service failure cannot become a zero-cost abstention.
        emit(store, dict(kind="unmetered_call", trial=assignment, prompt=req, elapsed_seconds=monotonic()-start,
                         error=str(exc), input_tokens=None, output_tokens=None))
        raise


def call_model(task, lang, trial, store, port, previous=None, feedback=None):
    req = request(task, lang, previous, feedback)
    start = monotonic()
    res = metered_reply(port, req, trial, store, start)
    elapsed = monotonic() - start
    raw = res["response"]
    try:
        parsed = json.loads(raw)
        expression = parsed["expression"] if isinstance(parsed, dict) and set(parsed) == {"expression"} else ""
    except (ValueError, KeyError):
        expression = ""
    if not isinstance(expression, str):
        expression = ""
    row = dict(kind="call", trial=trial, prompt=req, response=raw, model_seconds=elapsed,
               input_tokens=res["prompt_eval_count"], output_tokens=res["eval_count"], stop=res.get("done_reason"))
    emit(store, row)
    return expression, row


def trial(task, lang, arm, work, store, port):
    trial_id = "/".join((task.name, lang, arm))
    start = monotonic()
    path = work / "sketch.gpp"
    path.write_text(sketch(task))
    rules = [obligation(task)]
    calls = []
    last = None

    def check(expr, source):
        nonlocal last
        last = expr
        if lang == "gpp":
            return acceptance.check_candidate(BINARY, path, expr, source, rules, budget=BUDGET)
        return portable_check(lang, task, expr, source, work / "native")

    def propose(feedback):
        detail = compact_feedback(task, feedback) if feedback and arm != "direct_retry" else None
        previous = feedback["edit_site"].get("previous", feedback.get("previous", last)) if feedback else None
        expr, receipt = call_model(task, lang, trial_id, store, port, previous, detail)
        calls.append(receipt)
        return expr

    if arm in ("workflow", "search"):
        found = acceptance.search(BINARY, path, limit=LIMIT, budget=BUDGET)
        def authoritative_answer(inputs):
            xs = ordered_inputs(task, inputs)
            if lang != "gpp":
                question = found.get("question") or found["selection"]["longer_disagreement"]
                for alternative in question["alternatives"]:
                    expr = native.translate(alternative["expression"], lang)
                    value, = native.observe(lang, task, expr, [xs], work / "question")
                    expected = alternative["outcome"].get("result")
                    if type(value) is not type(expected) or value != expected:
                        raise LookupError("Native observer does not reproduce the proposed distinction")
            return public_answer(task, xs)

        authority = dict(source=f"public.py:public_answer/{task.name} within declared bounds",
                         answer=authoritative_answer)
        result = acceptance.run_policy(found, check, propose if arm == "workflow" else None,
                                       authority=authority if arm == "workflow" else None, render=lambda expr: native.translate(expr, lang))
    elif arm == "direct":
        expr = propose(None)
        row = check(expr, "model:initial")
        ok = row["decision"] == "accept"
        result = dict(decision="accept" if ok else "abstain", selected=expr if ok else None, first_pass=ok,
                      model_calls=1, candidates=[row], reason=row.get("reason"), question=None, search=None)
    else:
        result = acceptance.run_policy(dict(status="not_requested"), check, propose)
    if result["model_calls"] != len(calls):
        raise RuntimeError("Call count mismatch")
    elapsed = monotonic() - start
    model_sec = sum(c["model_seconds"] for c in calls)
    return dict(kind="trial", provenance="new_execution", trial=trial_id, task=task.name, language=lang, arm=arm,
                **result, wall_seconds=elapsed, model_seconds=model_sec, tool_seconds=elapsed-model_sec,
                input_tokens=sum(c["input_tokens"] for c in calls), output_tokens=sum(c["output_tokens"] for c in calls))


def roster():
    cells = [(task, lang, arm) for task in TASKS for lang in LANGUAGES for arm in ARMS]
    random.Random(7011).shuffle(cells)
    return cells


def preflight(work):
    """Check independently written reference and deliberate wrong edit against the actual property alone."""
    rows = []
    for task in TASKS:
        path = work / "calibrate.gpp"
        path.write_text(sketch(task))
        start = monotonic()
        results = {}
        for kind, expr in [("reference", task.reference), ("mutant", task.previous)]:
            # A trivial true contract lets the mutant reach the acceptance property regardless of example failure.
            module = sketch(task).split("contract sample_0")[0] + "contract available() { true }\n"
            path.write_text(module)
            rec = acceptance.check_candidate(BINARY, path, expr, f"calibration:{kind}", [obligation(task)])
            if rec["decision"] != ("accept" if kind == "reference" else "reject"):
                raise ValueError((task.name, kind, rec))
            results[kind] = rec
        # Exercise actual native evaluators against the independently authored public specification.
        domain = list(points(task))
        for lang in ("python", "rust"):
            for kind, expr in [("reference", task.reference), ("mutant", task.previous)]:
                native_expr = native.translate(expr, lang)
                actual = native.observe(lang, task, native_expr, domain, work / "preflight" / lang)
                ok = all(type(a) is type(b) and a == b for a, b in
                         zip(actual, (public_answer(task, x) for x in domain), strict=True))
                if ok != (kind == "reference"):
                    raise ValueError((task.name, lang, kind))
        rows.append(dict(task=task.name, seconds=monotonic()-start, public_assignments=len(domain), **results))
    return rows


def mutation_audit(work, port, store):
    """Meter a public-only attempt to falsify each acceptance property. Never feed audit edits to a trial."""
    start = monotonic()
    receipts = []
    for task in TASKS:
        path = work / "audit.gpp"
        path.write_text(sketch(task))
        req = request(task, "gpp")
        req["prompt"] += ("\nContract preparation. Propose an intentionally INCORRECT expression that passes the "
                          "listed examples and violates the rule elsewhere within the stated bounds.")
        call_start = monotonic()
        reply = metered_reply(port, req, "preparation/" + task.name, store, call_start)
        elapsed = monotonic() - call_start
        try:
            expr = json.loads(reply["response"])["expression"]
        except (TypeError, ValueError, KeyError):
            expr = ""
        row = dict(task=task.name, model_seconds=elapsed, input_tokens=reply["prompt_eval_count"],
                   output_tokens=reply["eval_count"], prompt=req, response=reply["response"])
        emit(store, dict(kind="preparation_call", **row))
        row["check"] = acceptance.check_candidate(BINARY, path, expr if isinstance(expr, str) else "",
                                                  "model:public mutation audit", [obligation(task)])
        receipts.append(row)
    return receipts, monotonic() - start


def collect(archive, port):
    freeze = verify_freeze()
    if archive.exists():
        raise FileExistsError(f"Choose a fresh output directory; {archive} exists")
    subprocess.run(["cargo", "build", "--release", "--locked", "--offline"], cwd=ROOT, check=True)
    tags = {m["name"]: m["digest"] for m in ollama(port, "tags")["models"]}
    if tags.get(MODEL) != MODEL_DIGEST:
        raise ValueError("Pinned Qwen build is required")
    archive.mkdir(parents=True)
    with TemporaryDirectory(prefix="checked-edits-") as temp, (archive / "decisions.jsonl").open("x") as store:
        work = Path(temp)
        emit(store, dict(kind="manifest", started_utc=utc(), freeze_sha256=digest(MANIFEST),
                         binary_sha256=digest(BINARY), model=MODEL, model_digest=MODEL_DIGEST,
                         platform=platform.platform(), assignments=len(roster()), prep=freeze["preparation"],
                         rust=subprocess.check_output(["rustc", "-V"], text=True).strip(),
                         mypy=subprocess.check_output([native.PYTHON, "-m", "mypy", "--version"], text=True).strip(),
                         python=sys.version, ollama_version=ollama(port, "version").get("version")))
        calibrated = preflight(work)
        audit, audit_wall = mutation_audit(work, port, store)
        emit(store, dict(kind="preflight", results=calibrated, mutation_audit=audit, audit_wall_seconds=audit_wall))
        for task, lang, arm in roster():
            with TemporaryDirectory(dir=work) as td:
                row = trial(task, lang, arm, Path(td), store, port)
            emit(store, row)
            print(row["trial"], row["decision"], flush=True)
        emit(store, dict(kind="closed", ended_utc=utc(), count=len(roster())))
    # The scorer is a separate process. It cannot supply inputs to a model call or revise a closed decision.
    subprocess.run([sys.executable, "-B", HERE / "score.py", archive], check=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("output", type=Path, help="new directory for prompts, evidence and paired scores")
    p.add_argument("--port", type=int, default=11434)
    args = p.parse_args()
    collect(args.output, args.port)
