"""Opt-in, revision-bound publication gate. Inputs are a public sketch and public rules."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
from tempfile import TemporaryDirectory
from time import monotonic

import probe
import propose



def revision(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _compiler(binary, *args, timeout=60):
    return subprocess.run([str(binary), *map(str, args)], capture_output=True, timeout=timeout)


def _report(result, schema, rev):
    if not result.stdout:
        raise ValueError(result.stderr.decode(errors="replace").strip() or "Compiler returned no record")
    row = json.loads(result.stdout)
    if not isinstance(row, dict) or row.get("schema") != schema or row.get("revision") != rev:
        raise ValueError(f"Unexpected {schema} record or stale compiler revision")
    return row


def search(binary, sketch, *, hole="change", limit=256, budget=10000):
    start = monotonic()
    rev = revision(Path(sketch).read_bytes())
    try:
        result = _compiler(binary, "complete", sketch, "--hole", hole, "--expect", rev,
                           "--search", "piecewise", "--limit", limit, "--budget", budget)
        report = _report(result, "gpp.complete/1", rev)
    except subprocess.TimeoutExpired:
        report = dict(revision=rev, hole=hole, status="timeout")
    report.update(source="compiler:complete/piecewise", tool_seconds=monotonic()-start)
    return report


def _obligation(contract):
    # Keep the source spelling of the binder list. In particular, never report a
    # wider domain than the one sent to the compiler (e.g. nonnegative I64).
    name = contract["name"]
    declaration = contract["declaration"]
    code = re.sub(r"//[^\n]*", "", declaration)
    header = re.search(r"\bcontract\s+" + re.escape(name) + r"\s*\(([^()]*)\)\s*\{", code)
    if not header or contract["mode"] not in {"finite", "prove"}:
        raise ValueError(f"Invalid public obligation {name!r}")
    return {**contract, "domain": header[1].strip(), "status": "not_run"}


def _replay(binary, path, site, span_end, contract, inputs, args, witness, rule):
    rev = revision(path.read_bytes())
    call = ["trace", path, "--function", site["function"], "--contract", contract,
            *[json.dumps(v) for v in args]]
    trace = _report(_compiler(binary, *call), "gpp.trace/1", rev)
    result = {k: trace[k] for k in ("fault", "result") if k in trace}
    if (trace.get("entry_kind") != "contract" or trace["args"] != args
            or not result or any(witness.get(k) != v for k, v in result.items())
            or ("fault" not in result and result != {"result": False})):
        raise ValueError("Published contract witness failed interpreter replay")
    node = next((e for e in trace.get("expressions", []) if isinstance(e, dict)
                 and (e.get("start_byte"), e.get("end_byte")) == (site["start_byte"], span_end)), None)
    if node is None or not isinstance(node.get("text"), str):
        raise ValueError("Trace did not identify the checked editable expression")
    observations = node.get("observations")
    if (not isinstance(observations, list) or type(node.get("hits")) is not int
            or len(observations) != min(3, node["hits"])
            or any(not isinstance(o, dict) or not isinstance(o.get("locals"), dict)
                   or ("value" in o) == ("fault" in o) for o in observations)):
        raise ValueError("Malformed runtime observations for the editable expression")
    # The session checks a byte-scoped no-op replacement on precisely this
    # revision, independently of trace's instrumented evaluator.
    calls = [(contract, [json.dumps(v) for v in args])]
    with probe.session(binary, path, site["function"], rev, path.parent, calls, contracts=True) as evaluate:
        replayed = evaluate(dict(start_byte=node["start_byte"], end_byte=span_end, replacement=node["text"]))
    if replayed.get("outcomes") != [result]:
        raise ValueError("Probe and trace disagree on the public counterexample")
    return dict(contract=contract, rule=rule, inputs=inputs, args=args, contract_result=result,
                observed=node["observations"], edit_site={**site, "previous": node["text"]},
                replay={"source_revision": rev, "probe": replayed["outcomes"][0], "command": [str(x) if x != path else "CANDIDATE.gpp"
                                                           for x in call]})


def _check(binary, sketch, work, record, hole, budget, timeout_ms):
    data = sketch.read_bytes()
    rev = record["sketch_revision"]
    holes = _report(_compiler(binary, "holes", sketch), "gpp.holes/1", rev)["holes"]
    if len(holes) != 1 or holes[0]["name"] != hole:
        raise ValueError("Expected exactly one checked editable expression hole")
    site = {**holes[0], "revision": rev}
    record["edit_site"] = site
    fragment = work / "edit.expr"
    if not isinstance(record["expression"], str):
        record.update(decision="reject", reason="invalid_expression",
                      feedback={"edit_site": site, "diagnostic": "Expected a single expression string."})
        return
    fragment.write_text(record["expression"], encoding="utf-8")

    def fill(path, expected, assignment_limit):
        proc = _compiler(binary, "complete", path, "--hole", hole, "--fill", fragment, "--expect", expected,
                         "--budget", assignment_limit)
        return _report(proc, "gpp.complete/1", expected)

    completed = fill(sketch, rev, budget)
    suffix = b""
    if completed.get("reason") == "no_contracts":
        # complete --fill needs an obligation to visit the typed hole. Give it
        # a constant predicate on an isolated copy; it supplies no public label.
        marker = "acceptance_typecheck"
        while marker.encode() in data:
            marker += "_"
        suffix = f"\ncontract {marker}() {{ true }}\n".encode()
        typed = work / "typecheck.gpp"
        typed.write_bytes(data + suffix)
        completed = fill(typed, revision(data + suffix), 1)
        record.update(public_examples={"status": "not_provided", "checked": 0, "contracts": []},
                      typecheck_sentinel=True)
    examples = completed.get("verification")
    if not examples:
        detail = completed.get("diagnostic", completed.get("reason", completed["status"]))
        record["reason"] = detail
        if "diagnostic" in completed:
            record.update(decision="reject", feedback={"edit_site": site, "previous": record["expression"],
                                                       "diagnostic": detail})
        return
    # Materialize the scoped edit even when a public example failed so trace
    # can replay the first rejection. complete's type gate checked the hole type.
    preview = _compiler(binary, "edit", sketch, "--function", site["function"], "--at",
                        f"{site['start_byte']}:{site['end_byte']}", "--expr", fragment,
                        "--expect", rev, "--stdout")
    if preview.returncode or revision(preview.stdout + suffix) != examples["revision"]:
        raise ValueError("Revision-checked editor and typed completion disagree")
    candidate = work / "candidate.gpp"
    candidate.write_bytes(preview.stdout)
    span_end = len(preview.stdout) - (len(data) - site["end_byte"])
    record["candidate_revision"] = revision(preview.stdout)
    if not suffix:
        record["public_examples"] = examples
    if examples["status"] == "counterexample":
        failure = next(x for x in examples["contracts"] if x["status"] == "counterexample")
        name, w = failure["name"], failure["counterexample"]
        # Let the compiler locate the failed check; quote its actual public rule.
        module = re.sub(r"//[^\n]*", "", data.decode())
        match = re.search(r"\bcontract\s+" + re.escape(name) + r"\b[^{}]*\{([^{}]*)\}", module)
        rule = match[0].strip() if match else name
        record.update(decision="reject", reason="public_example",
                      feedback=_replay(binary, candidate, site, span_end, name, w["inputs"], w["args"], w, rule))
        return
    if examples["status"] != "passed" or not examples["checked"]:
        record["reason"] = examples.get("reason", "examples_incomplete")
        return
    if not record["obligations"]:
        record["reason"] = "no_acceptance_contract"
        return
    module = preview.stdout + b"\n" + "\n".join(c["declaration"] for c in record["obligations"]).encode() + b"\n"
    candidate.write_bytes(module)
    verified_rev = revision(module)
    record["verification_revision"] = verified_rev
    for contract in record["obligations"]:
        name = contract["name"]
        finite = contract["mode"] == "finite"
        if finite:
            proc = _compiler(binary, "verify", candidate, "--contract", name, "--budget", budget, "--format=json")
            row = _report(proc, "gpp.verify/1", verified_rev)
        else:
            proc = _compiler(binary, "prove", candidate, "--contract", name, "--timeout-ms", timeout_ms,
                             timeout=2*timeout_ms/1000 + 5)
            row = _report(proc, "gpp.prove/1", verified_rev)
        if len(row["contracts"]) != 1 or row["contracts"][0]["name"] != name:
            raise ValueError("Requested contract absent from compiler result")
        contract.update(row["contracts"][0])
        if contract["status"] in {"counterexample", "refuted"}:
            w = contract["counterexample"]
            args = w.get("args", list(w["inputs"].values()))
            feedback = _replay(binary, candidate, site, span_end, name, w["inputs"], args, w, contract["rule"])
            record.update(decision="reject", reason="contract_counterexample", feedback=feedback)
            return
        if contract["status"] != ("passed" if finite else "proved"):
            record["reason"] = contract.get("reason", contract["status"])
            return
    record.update(decision="accept", reason="declared_contracts_discharged")


def check_candidate(binary, sketch, expression, source, contracts, *, hole="change", budget=10000, timeout_ms=5000):
    """Check a restricted fill. Only discharged named obligations permit automatic acceptance."""
    start = monotonic()
    sketch = Path(sketch)
    data = sketch.read_bytes()
    record = dict(schema="gpp.acceptance/1", source=source, expression=expression, sketch_revision=revision(data),
                  decision="abstain", public_examples={"status": "not_run"}, feedback=None,
                  edit_site=None, budget_per_finite_verification=budget, proof_timeout_ms=timeout_ms,
                  obligations=[_obligation(c) for c in contracts])
    try:
        with TemporaryDirectory(prefix="gpp-accept-") as tmp:
            work = Path(tmp)
            snapshot = work / "public.gpp"
            snapshot.write_bytes(data)
            _check(binary, snapshot, work, record, hole, budget, timeout_ms)
    except subprocess.TimeoutExpired as exc:
        for c in record["obligations"]:
            if "--contract" in exc.cmd and c["name"] == exc.cmd[exc.cmd.index("--contract")+1]:
                c["status"] = "timeout"
        record.update(decision="abstain", reason="tool_timeout", feedback=None)
    except (ValueError, KeyError, TypeError, StopIteration, OSError, propose.ProposalError) as exc:
        record.update(decision="abstain", reason="tool_error", detail=str(exc), feedback=None)
    if sketch.read_bytes() != data:
        record.update(decision="abstain", reason="stale_revision", feedback=None)
    record["tool_seconds"] = monotonic() - start
    return record


def resolve_question(question, authority):
    """One distinguishing call. A reference may decline inputs outside its authorized domain."""
    receipt = dict(question=question, status="unresolved", answer=None, source=None, labels=0,
                   calls=0, elapsed_seconds=0, input_tokens=0, output_tokens=0)
    if authority is None:
        receipt["reason"] = "no_authorized_source"
        return receipt
    receipt.update(source=authority["source"], calls=1)
    started = monotonic()
    try:
        answer = authority["answer"](dict(question["inputs"]))
    except LookupError:
        answer = None
    except (TimeoutError, subprocess.TimeoutExpired):
        receipt["reason"] = "source_timeout"
        return receipt
    except (ValueError, OSError, propose.ProposalError) as exc:
        receipt.update(reason="source_error", detail=str(exc))
        return receipt
    finally:
        receipt["elapsed_seconds"] = monotonic() - started
    if isinstance(answer, dict) and "value" in answer:
        receipt.update({k: answer[k] for k in ("input_tokens", "output_tokens") if k in answer})
        answer = answer["value"]
    if answer is None:
        receipt["reason"] = "source_declined"
        return receipt
    matches = [i for i, alt in enumerate(question["alternatives"])
               if "result" in alt["outcome"] and type(alt["outcome"]["result"]) is type(answer)
               and alt["outcome"]["result"] == answer]
    receipt.update(answer=answer, labels=1, matches=matches)
    if len(matches) == 1:
        receipt["status"] = "answered"
    else:
        receipt["reason"] = "answer_does_not_select_one"
    return receipt


def run_policy(search_report, check, propose_model, *, authority=None, render=lambda expression: expression):
    """Choose from public evidence only. Feedback-bearing rejection buys at most one model repair."""
    outcome = dict(schema="gpp.acceptance-workflow/1", decision="abstain", selected=None, first_pass=False,
                   model_calls=0, candidates=[], search=search_report, question=None)

    def evaluate(expr, source):
        row = check(expr, source)
        outcome["candidates"].append(row)
        return row

    def accept(row, first):
        outcome.update(decision="accept", selected=row["expression"], first_pass=first,
                       reason="declared_contracts_discharged")
        return outcome

    question = search_report.get("question") or search_report.get("selection", {}).get("longer_disagreement")
    if question:
        rows = [evaluate(render(a["expression"]), "compiler:complete/piecewise")
                for a in question["alternatives"]]
        # If the rules themselves eliminate the other alternatives, nothing needs labeling.
        remaining = [r for r in rows if r["decision"] != "reject"]
        if len(remaining) == 1 and remaining[0]["decision"] == "accept":
            return accept(remaining[0], True)
        if remaining:
            receipt = resolve_question(question, authority)
            outcome["question"] = receipt
            if receipt["status"] == "answered":
                selected = rows[receipt["matches"][0]]
                if selected["decision"] == "accept":
                    return accept(selected, True)
            outcome["reason"] = "unresolved_ambiguity"
            return outcome
        row = rows[0]
    elif search_report.get("selected") is not None:
        row = evaluate(render(search_report["selected"]), "compiler:complete/piecewise")
    elif search_report["status"] == "ambiguous":
        outcome["reason"] = "unresolved_ambiguity"
        return outcome
    else:
        if propose_model is None:
            outcome["reason"] = "no_compiler_candidate"
            return outcome
        outcome["model_calls"] += 1
        row = evaluate(propose_model(None), "model:initial")

    if row["decision"] == "accept":
        return accept(row, True)
    feedback = row.get("feedback")
    if feedback and "observed" in feedback and not feedback["observed"]:
        outcome["reason"] = "failure_outside_edit_site"
        return outcome
    if propose_model is not None and row["decision"] == "reject" and feedback:
        outcome["model_calls"] += 1
        row = evaluate(propose_model(row["feedback"]), "model:repair")
        if row["decision"] == "accept":
            return accept(row, False)
    outcome["reason"] = row.get("reason", "no_validated_edit")
    return outcome


def run_workflow(binary, sketch, contracts, propose_model, *, authority=None, hole="change",
                 limit=256, budget=10000, timeout_ms=5000):
    sketch = Path(sketch)
    data = sketch.read_bytes()
    with TemporaryDirectory(prefix="gpp-workflow-") as tmp:
        snapshot = Path(tmp) / "public.gpp"
        snapshot.write_bytes(data)
        found = search(binary, snapshot, hole=hole, limit=limit, budget=budget)

        def check(expression, source):
            return check_candidate(binary, snapshot, expression, source, contracts, hole=hole,
                                   budget=budget, timeout_ms=timeout_ms)

        outcome = run_policy(found, check, propose_model, authority=authority)
    if sketch.read_bytes() != data:
        outcome.update(decision="abstain", selected=None, first_pass=False, reason="stale_revision")
    return outcome


def model_request(model, task, site, feedback):
    """Public specification + the editable token range and, on a retry, its replay."""
    prompt = [
        "Fill one typed GPT++ expression. Return a JSON object containing only expression.",
        task, f"Function {site['function']}. Result type {site['type']}.",
        "In scope: " + ", ".join(f"{v['name']}: {v['type']}" for v in site["locals"]),
    ]
    if feedback:
        previous = feedback["edit_site"].get("previous", feedback.get("previous", ""))
        prompt.append("Replace this expression: " + previous)
        if "contract" in feedback:
            prompt.extend([feedback["rule"], "Failing public contract input: " + json.dumps(feedback["inputs"]),
                           "Observed expression evaluations: " + json.dumps(feedback["observed"]),
                           "Public contract outcome: " + json.dumps(feedback["contract_result"])])
        else:
            prompt.append(feedback["diagnostic"])
    return dict(model=model, prompt="\n".join(prompt), stream=False, keep_alive="3m",
                format={"type": "object", "properties": {"expression": {"type": "string"}},
                        "required": ["expression"], "additionalProperties": False},
                options={"temperature": 0, "seed": 42, "num_ctx": 4096, "num_predict": 160})


def local_proposer(binary, sketch, task, hole, model, port, calls):
    """Delay contacting Ollama until a decision actually consumes a model call."""
    def generate(feedback):
        site = next(h for h in json.loads(propose.checked(binary, "holes", sketch))["holes"]
                    if h["name"] == hole)
        name, _, _, digest = propose.local_model(model, port)
        request = model_request(name, task, site, feedback)
        start = monotonic()
        reply = propose.ollama(port, "generate", request)
        elapsed = monotonic() - start
        fields = ("response", "done", "done_reason", "prompt_eval_count", "eval_count")
        calls.append(dict(request=request, reply={k: reply.get(k) for k in fields}, digest=digest,
                          elapsed_seconds=elapsed))
        if not reply.get("done") or any(type(reply.get(k)) is not int for k in fields[-2:]):
            raise ValueError("Incomplete model generation or missing token usage")
        try:
            data = json.loads(reply["response"])
            if isinstance(data, dict) and isinstance(data.get("expression"), str):
                return data["expression"]
        except ValueError:
            pass
        return ""  # Invalid output still goes through the same public gate and costs ledger.
    return generate


def public_reference(binary, path, function):
    """Load the exact authorized source; ask it at most once per run_policy call."""
    data = Path(path).read_bytes()
    rev = revision(data)

    def answer(inputs):
        with TemporaryDirectory(prefix="gpp-public-reference-") as tmp:
            reference = Path(tmp) / "authorized.gpp"
            reference.write_bytes(data)
            call = [json.dumps(v) for v in inputs.values()]
            trace = _report(_compiler(binary, "trace", reference, "--function", function, "--call",
                                      function, *call), "gpp.trace/1", rev)
            return trace.get("result")
    return {"source": f"{path} @ {rev}::{function}", "answer": answer}


def main():
    import argparse
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("sketch", type=Path, help="one typed hole plus public example contracts")
    cli.add_argument("--contracts", type=Path, required=True, help="predeclared public acceptance obligations (JSON)")
    cli.add_argument("--task", required=True, help="plain-language public specification")
    cli.add_argument("--hole", default="change")
    cli.add_argument("--model", help="locally installed Ollama model (omit for compiler only)")
    cli.add_argument("--port", type=int, default=11434)
    cli.add_argument("--reference", type=Path, help="authorized total GPT++ reference with the same target signature")
    cli.add_argument("--gpp", default=str(propose.ROOT / "target/release/gpp"))
    args = cli.parse_args()
    calls = []
    model = local_proposer(args.gpp, args.sketch, args.task, args.hole, args.model, args.port, calls) if args.model else None
    auth = None
    if args.reference:
        site = next(h for h in json.loads(propose.checked(args.gpp, "holes", args.sketch))["holes"]
                    if h["name"] == args.hole)
        auth = public_reference(args.gpp, args.reference, site["function"])
    outcome = run_workflow(args.gpp, args.sketch, json.loads(args.contracts.read_text()), model,
                           authority=auth, hole=args.hole)
    print(json.dumps({**outcome, "model_usage": calls}, indent=2))


if __name__ == "__main__":
    main()
