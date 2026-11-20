#!/usr/bin/env python3
"""Generate a new checked expression from a specification, with one public diagnostic retry."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
import time

from indexed_edit import edit_request as catalog_request, order_spans, read_change
import propose


GUIDES = {
    "gpp": ("GPT++", "if condition { yes } else { no }", "&&, ||, !", "/"),
    "rust": ("Rust", "if condition { yes } else { no }", "&&, ||, !", "/"),
    "python": ("typed Python", "yes if condition else no", "and, or, not", "//"),
}


def request_for(model, language, task, examples, target, spans, callers, previous=None):
    payload = catalog_request(model, language, task, examples, target, spans)
    name, conditional, logic, divide = GUIDES[language]
    data = target.encode()
    choices = [f"[{i}] {data[a:b].decode()}" for i, (a, b) in enumerate(spans, 1)]
    prompt = [
        f"You maintain a {name} program. Correct the target function for every input in its contract.",
        "Change request", task, "Target", target, "Read-only caller context", callers or "(none)",
        "Starter execution on the supplied examples", *examples,
        "Select a numbered expression from the target and replace it with one expression.",
        "Expression IDs (each refers to the original unchanged source):", *choices,
        f"Native expressions: conditional `{conditional}`; Boolean logic `{logic}`; integer division `{divide}`.",
        "Use the target's parameters, local variables and integer arithmetic. Keep unaffected branches intact.",
        "Do not call the target or its callers. Do not copy the example inputs into the program.",
        'Return only {"site":"ID","replacement":"native expression"}. The editor supplies parentheses.',
    ]
    if previous is not None:
        old, diagnostic = previous
        prompt.extend(["Your previous change did not pass validation:", old, "Diagnostic:", diagnostic,
                       "Revise the site or expression against the original target."])
    payload["prompt"] = "\n".join(prompt)
    payload["options"].update(num_ctx=4096, num_predict=240, seed=42 if previous is None else 43)
    return payload


def diagnostic(detail):
    # OS thread IDs in Rust panic diagnostics vary between identical invocations.
    return re.sub(r"(thread 'main' )\([0-9]+\)", r"\1(worker)", detail.strip())[:600]


def attempts(model, language, task, examples, target, spans, callers, generate, validate):
    previous, logs = None, []
    for _ in range(2):
        request = request_for(model, language, task, examples, target, spans, callers, previous)
        start = time.monotonic()
        reply = generate(request)
        model_ms = round((time.monotonic() - start) * 1000)
        if reply.get("done") is not True or not isinstance(reply.get("response"), str):
            raise ValueError("Ollama returned an incomplete generation.")
        raw = reply["response"]
        checked_at = time.monotonic()
        patch, span, expression = None, None, None
        try:
            span, expression = read_change(raw, spans)
            status, detail, patch = validate(span, expression.strip())
        except (ValueError, RecursionError) as exc:
            status, detail = "invalid_selection", str(exc)
        detail = diagnostic(detail)
        logs.append({"request": request, "reply": {k: reply[k] for k in (
                         "response", "done_reason", "prompt_eval_count", "eval_count") if k in reply},
                     "model_ms": model_ms, "validation_ms": round((time.monotonic() - checked_at) * 1000),
                     "span": list(span) if span else None, "replacement": expression, "status": status,
                     "detail": detail, "patch_sha256": sha256(patch).hexdigest() if patch is not None else None})
        if status == "pass":
            return logs, patch
        previous = raw, detail
    return logs, None


def propose_edit(args):
    if not args.task.strip() or os.path.lexists(args.output) or not args.output.parent.is_dir():
        raise ValueError("Supply a nonempty task and a new fragment path in an existing directory.")
    source = args.file.read_bytes()
    with TemporaryDirectory(prefix="gpp-agent-edit-") as scratch:
        work = Path(scratch)
        snapshot, fragment = work / "base.gpp", work / "change.expr"
        snapshot.write_bytes(source)
        revision = propose.checked(args.gpp, "revision", snapshot).strip()
        catalog = propose.expression_catalog(args.gpp, snapshot, args.function, revision)
        start, end = catalog["start_byte"], catalog["end_byte"]
        spans = order_spans((e["start_byte"] - start, e["end_byte"] - start) for e in catalog["expressions"])
        dump = propose.checked(args.gpp, "ast", snapshot)
        decls = {f["name"]: f for f in propose.FUNCTION.finditer(dump)}
        cases = propose.load_cases(args.cases, args.function, decls)
        examples = []
        for c in cases:
            trace = json.loads(propose.checked(args.gpp, "trace", snapshot, "--function", args.function,
                                               "--call", c.function, *c.args))
            actual = trace.get("fault") or propose.case_literal(trace["result"], c.result_type, "result")
            examples.append(f"{c.call()} returned {actual}; expected {c.expected}.")
        callers = propose.caller_section(decls, args.function).strip()
        model, *_ = propose.local_model(args.model, args.port)

        def command(span, path):
            a, b = span
            return [str(args.gpp), "edit", str(path), "--function", args.function, "--at",
                    f"{start + a}:{start + b}", "--expr"]

        def validate(span, expression):
            fragment.write_text(expression + "\n")
            proc = propose.compiler(*command(span, snapshot), fragment, "--expect", revision, "--stdout")
            if proc.returncode:
                error = proc.stderr.decode(errors="replace").strip().replace(str(work) + "/", "")
                if "error[GPP-" not in error:
                    raise propose.ProposalError(error)
                return "check_error", error, None
            try:
                propose.check_cases(args.gpp, proc.stdout, work, cases)
            except propose.CaseFailure as exc:
                status = "runtime_error" if " failed during execution." in exc.compact else "wrong_answer"
                return status, exc.compact, proc.stdout
            return "pass", "", proc.stdout

        logs, patch = attempts(model, "gpp", args.task, examples, source[start:end].decode(),
                              spans, callers, lambda req: propose.ollama(args.port, "generate", req), validate)
        if propose.checked(args.gpp, "revision", args.file).strip() != revision:
            raise ValueError("Source changed during generation.")
        result = {"schema": "gpp.agent-edit/1", "function": args.function, "revision": revision,
                  "status": "proposed" if patch is not None else "rejected", "attempts": logs}
        if patch is not None:
            last = logs[-1]
            result["apply"] = [*command(last["span"], args.file), str(args.output), "--expect", revision]
            propose.publish(args.output, last["replacement"].strip() + "\n")
        if not args.transcript:
            for a in logs:
                a.pop("request")
                a["reply"].pop("response")
        return result


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("file", type=Path)
    cli.add_argument("--function", required=True)
    cli.add_argument("--task", required=True)
    cli.add_argument("--cases", required=True, type=Path)
    cli.add_argument("--gpp", default=str(propose.ROOT / "target/debug/gpp"))
    cli.add_argument("--model", default=propose.MAINTENANCE_MODEL)
    cli.add_argument("--port", type=int, default=11434)
    cli.add_argument("--transcript", action="store_true", help="include inference prompts and raw completions")
    cli.add_argument("-o", "--output", type=Path, required=True)
    try:
        print(json.dumps(propose_edit(cli.parse_args()), ensure_ascii=False))
    except (OSError, subprocess.TimeoutExpired, ValueError, propose.ProposalError) as exc:
        sys.exit(str(exc))


if __name__ == "__main__":
    main()
