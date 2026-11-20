#!/usr/bin/env python3
"""Use a locally installed Ollama model to draft a checked GPT++ function fragment."""

import argparse
import ast
from dataclasses import dataclass
import difflib
import http.client
import json
import keyword
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap

from caller_context import _braced_calls, caller_context
from obligation_feedback import obligation_text, public_obligation
from policy_ir import lower_policy
from scalar_builtins import lower_fragment


ROOT = Path(__file__).resolve().parents[1]
FENCE = chr(96) * 3
SCALAR_TYPES = {"I64": "int", "Bool": "bool"}
POLICY_PREFIX = "when "
POLICY_SUFFIX = "\nelse => @keep\n"
MAINTENANCE_MODEL = "qwen2.5-coder:7b"
# The v7 StarCoder2 artifact uses a plain prompt template and raw BigCode FIM tokens.
STAR_FIM_DIGEST = "f67ae0f64584a4d1d7c609bf4778dd0d07054582362d21ca4f0eddea22aafd0c"
STAR_STOPS = ["<file_sep>", "<fim_prefix>", "<fim_suffix>", "<fim_middle>", "<|endoftext|>"]
BOUNDARY_STOPS = {
    "gpp": ["\n}"],
    "python": ["\ndef ", "\nclass ", "\nimport ", "\nfrom ", "\nassert ", "\nprint(", "\nif __name__", "\n@"],
    "policy": ["\nelse", "\n#", FENCE],
}
# Read the compiler's normalized AST dump, whose top-level closing braces are
# flush left. Comments in the source (including braces) are absent from it.
FUNCTION = re.compile(
    r"^(?P<header>(?:pub )?fn (?P<name>[A-Za-z_][A-Za-z_0-9]*)\((?P<params>[^\n)]*)\)"
    r" -> (?P<result>I64|Bool|Unit) !\{\}) \{\n(?P<body>.*?)^\}$", re.M | re.S,
)


class ProposalError(Exception):
    pass


class CaseFailure(ValueError):
    def __init__(self, case, message, compact):
        super().__init__(message)
        self.case = case
        self.function = case.function
        self.compact = compact


def compiler(binary, *args):
    return subprocess.run([binary, *map(str, args)], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=60, check=False)


def checked(binary, *args):
    result = compiler(binary, *args)
    if result.returncode:
        raise ProposalError(result.stderr.decode(errors="replace").strip())
    return result.stdout.decode("utf-8")


def ollama(port, endpoint, payload=None):
    # A direct loopback connection avoids environment proxies and URL redirects.
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=180)
    try:
        body = json.dumps(payload).encode() if payload is not None else None
        conn.request("POST" if body else "GET", "/api/" + endpoint, body,
                     {"Content-Type": "application/json"})
        reply = conn.getresponse()
        data = reply.read()
        if reply.status != 200:
            raise ProposalError(f"Ollama {endpoint} returned HTTP {reply.status}: "
                                + data.decode(errors="replace")[:500])
        value = json.loads(data)
        if not isinstance(value, dict) or value.get("error"):
            raise ProposalError(f"Invalid Ollama {endpoint} response: {str(value)[:300]}")
        return value
    finally:
        conn.close()


def local_model(name, port, maintenance=False):
    models = ollama(port, "tags").get("models", [])
    installed = next((entry for entry in models
                      if entry.get("name") in (name, name + ":latest")), None)
    if installed is None:
        hint = f". For the maintenance preset, install the tested model with: ollama pull {MAINTENANCE_MODEL}" if maintenance else ""
        raise ProposalError(f"{name!r} is not in this Ollama server's installed model list" + hint)
    selected = installed["name"]
    if installed.get("remote_model") or installed.get("remote_host"):
        raise ProposalError(f"{selected!r} uses a remote model")
    shown = ollama(port, "show", {"model": selected})
    if shown.get("remote_model") or shown.get("remote_host"):
        raise ProposalError(f"{selected!r} uses a remote model")
    template = shown.get("template")
    if not isinstance(template, str) or not template.strip():
        raise ProposalError(f"Ollama did not return a completion template for {selected!r}")
    return selected, template, shown.get("parameters", ""), installed.get("digest")


def generation_stops(model_parameters, surface, extra=()):
    # Ollama renders each installed stop string as a JSON-quoted parameter.
    if not isinstance(model_parameters, str):
        raise ProposalError("Ollama returned an invalid model parameter list")
    defaults = []
    for line in model_parameters.splitlines():
        parts = line.split(None, 1)
        if parts[:1] != ["stop"]:
            continue
        try:
            value = json.loads(parts[1]) if len(parts) == 2 else None
        except ValueError as exc:
            raise ProposalError("Invalid stop parameter in Ollama model metadata") from exc
        if not isinstance(value, str):
            raise ProposalError("Invalid stop parameter in Ollama model metadata")
        defaults.append(value)
    return list(dict.fromkeys(defaults + list(extra) + BOUNDARY_STOPS[surface]))


def target_context(dump, name):
    declarations = list(FUNCTION.finditer(dump))
    targets = [fn for fn in declarations if fn["name"] == name]
    if len(targets) != 1:
        raise ProposalError(f"Expected one checked function named {name!r}, found {len(targets)}")
    return targets[0], [fn["header"] for fn in declarations if fn["name"] != name]


def caller_section(declarations, target):
    records = [{"name": f["name"], "signature": f["header"], "body": f["body"]}
               for f in declarations.values()]
    excerpt = caller_context(records, target, "gpp")
    return "\n" + excerpt if excerpt else ""


def is_caller(declarations, function, target):
    """Does this distinct checked function have a call path to the target?"""
    if function == target:
        return False
    pending = [function]
    seen = {function}
    while pending:
        body = declarations[pending.pop()]["body"]
        for callee, _, _ in _braced_calls(body, declarations, "gpp"):
            if callee == target:
                return True
            if callee not in seen:
                seen.add(callee)
                pending.append(callee)
    return False


def parameters(fn):
    return [tuple(decl.split(": ")) for decl in fn["params"].split(", ") if decl]


def scalar_parameters(fn, surface):
    if fn["result"] not in SCALAR_TYPES:
        raise ProposalError(f"The {surface} surface requires an I64 or Bool result.")
    params = []
    for name, kind in parameters(fn):
        if kind not in SCALAR_TYPES or keyword.iskeyword(name):
            raise ProposalError(f"Parameter {name}: {kind} cannot be expressed in the {surface} surface.")
        params.append((name, SCALAR_TYPES[kind]))
    return params


def python_declaration(fn):
    if keyword.iskeyword(fn["name"]):
        raise ProposalError("The scalar Python surface requires a Python function name.")
    params = scalar_parameters(fn, "scalar Python")
    annotated = ", ".join(f"{name}: {kind}" for name, kind in params)
    return f"def {fn['name']}({annotated}) -> {SCALAR_TYPES[fn['result']]}:", params


def maintenance_context(fn, task, cases, prepend, failure=()):
    parts = [task, "Examples", *(f"{c.call()} = {c.expected}" for c in cases[:3]), *failure]
    if prepend:
        parts.append("Insert early returns for changed cases above the existing body.")
    else:
        parts.extend(["Replace the current body", textwrap.dedent(fn["body"]).strip()])
    parts.append("GPT++ uses if flag { return value; }, let for constants and var for mutable locals.")
    return "\n".join(line for part in parts for line in part.splitlines())


def generation_context(fn, other, args, cases):
    if args.maintenance:
        return maintenance_context(fn, args.task, cases, args.prepend), fn["header"] + " {\n    ", []
    prompt = args.task + "\nCurrent GPT++ implementation:\n" + fn.group(0)
    if args.surface == "policy":
        prompt += ("\nWrite one row per changed case: when <condition> => <value>. First match wins."
                   "\nUse Python expressions: True, False, and, or, not, //, min, max, abs.")
        if args.infill:
            prompt += " The final else => @keep runs the current body."
        else:
            prompt += " Finish with 'else => <value>' or 'else => @keep' to keep the old behavior."
        return prompt, POLICY_PREFIX if args.infill else "", scalar_parameters(fn, "policy")
    header = fn["header"] + " {"
    params = []
    if args.surface == "python":
        prompt += ("\nUse scalar Python syntax with checked I64 and Bool. "
                   "// truncates toward zero and % follows the dividend. Use scalar operators, local variables, "
                   "and integer abs(x), min(x, y), max(x, y).")
        header, params = python_declaration(fn)
    else:
        if other:
            prompt += "\nAvailable functions:\n" + "\n".join(other)
        if args.form == "expr":
            prompt += f"\nComplete one {fn['result']} expression. Conditional: if flag {{ x }} else {{ y }}."
        else:
            prompt += ("\nComplete the function body with GPT++ statements. "
                       "Example: var i = 0; while i < n { i += 1; } return i;")
    prefix = header + "\n    " + ("return " if args.form == "expr" else "")
    return prompt, prefix, params


def complete(model, template, prefix, context, args, stops, retry, raw_fim=False, protected_body=None):
    options = {"seed": 43 if retry else 42, "temperature": 0.25 if retry else 0, "num_predict": 240}
    request = {"model": model, "stream": False, "keep_alive": "2m", "options": options}
    if args.maintenance:
        options["num_ctx"] = 2048
        request["keep_alive"] = "3m"
    if args.infill:
        if stops is not None:
            options["stop"] = stops
        comment = "//" if args.surface == "gpp" else "#"
        request["prompt"] = "".join(f"{comment} {line}\n" for line in context.splitlines()) + prefix
        suffix = {"policy": POLICY_SUFFIX, "python": "\n\n# End of function\n",
                  "gpp": (";" if args.form == "expr" else "") + "\n}\n"}
        if protected_body is not None:
            suffix["gpp"] = "\n" + protected_body + "\n}\n"
        if raw_fim:
            request.update(raw=True, prompt="<fim_prefix>" + request["prompt"]
                           + "<fim_suffix>" + suffix[args.surface] + "<fim_middle>")
        else:
            request["suffix"] = suffix[args.surface]
    else:
        marker = "{{ .Response }}"
        start = FENCE + args.surface + "\n" + prefix + marker
        request.update(prompt=context, system="Complete the supplied code. End the code block with a closing fence.",
                       template=(template.replace(marker, start, 1) if marker in template else template + start))
        options["stop"] = list(dict.fromkeys((stops or []) + [FENCE, "<|eot_id|>", "<｜end▁of▁sentence｜>"]))
    result = ollama(args.port, "generate", request)
    if result.get("done") is not True or not isinstance(result.get("response"), str):
        raise ProposalError("Ollama did not return a completed generation")
    return result["response"]


def fragment(suffix, form):
    """Remove only a prefilled function closer and optional expression terminator."""
    tokens = [(m[0], m.start()) for m in re.finditer(r"//[^\r\n]*|[^\s]", suffix)
              if not m[0].startswith("//")]
    # Ordinary balanced expression or statement braces belong to the model.
    if tokens and tokens[-1][0] == "}" and sum((s == "{") - (s == "}") for s, _ in tokens) == -1:
        _, at = tokens.pop()
        suffix = suffix[:at] + suffix[at + 1:]
    if tokens and form == "expr" and tokens[-1][0] == ";":
        _, at = tokens.pop()
        suffix = suffix[:at] + suffix[at + 1:]
    if not tokens:
        raise ValueError("Completion contained no code.")
    return suffix.strip() + "\n"


def projected_fragment(raw, form, params):
    if form == "body":
        # The source prefix already indents the first line. Parse a complete
        # function so a dedent cannot silently introduce a second declaration.
        first = raw[4:] if raw.startswith("    ") else raw
        try:
            suite = ast.parse("def fragment():\n    " + first)
        except SyntaxError as exc:
            raise ValueError(f"line {exc.lineno}, column {exc.offset}: {exc.msg}") from exc
        if len(suite.body) != 1 or not isinstance(suite.body[0], ast.FunctionDef):
            raise ValueError("Completion left the protected Python function body.")
        raw = "\n".join(ast.unparse(stmt) for stmt in suite.body[0].body)
    return lower_fragment(raw, form, params) + "\n"


def canonical_fragment(binary, preview, work, function, form):
    proposed = work / "proposed.gpp"
    proposed.write_bytes(preview)
    fn, _ = target_context(checked(binary, "ast", proposed), function)
    body = textwrap.dedent(fn["body"]).strip()
    if form == "expr":
        match = re.fullmatch(r"return (.+);", body)
        if not match:
            raise ProposalError("Compiler AST did not contain exactly one returned expression.")
        body = match[1]
    return body + "\n"


def case_literal(value, kind, location):
    if kind == "I64" and type(value) is int and -(2**63) <= value < 2**63:
        return str(value)
    if kind == "Bool" and type(value) is bool:
        return "true" if value else "false"
    if kind == "Unit" and value is None:
        return "()"
    raise ProposalError(f"{location} must be {kind} (I64 uses signed 64-bit integers).")


@dataclass(frozen=True)
class Case:
    function: str
    result_type: str
    args: list
    named: str
    expected: str

    def call(self):
        return f"{self.function}({', '.join(self.args)})"


def load_cases(path, target, declarations):
    if path is None:
        return []

    def unique_fields(pairs):
        fields = dict(pairs)
        if len(fields) != len(pairs):
            raise ProposalError(f"{path}: duplicate field in a case")
        return fields

    rows = json.loads(path.read_bytes(), object_pairs_hook=unique_fields)
    if not isinstance(rows, list) or not rows:
        raise ProposalError(f"{path}: expected a nonempty JSON list of cases")
    cases = []
    for index, row in enumerate(rows, 1):
        label = f"Case {index}"
        if not isinstance(row, dict) or set(row) not in ({"args", "expected"}, {"function", "args", "expected"}):
            raise ProposalError(f"{label} requires args and expected and accepts an optional function name")
        name = row.get("function", target)
        if not isinstance(name, str) or name not in declarations:
            raise ProposalError(f"{label} names an unknown function: {name!r}")
        fn = declarations[name]
        params = parameters(fn)
        if not isinstance(row["args"], list) or len(row["args"]) != len(params):
            raise ProposalError(f"{label} requires {len(params)} positional arguments for {fn['name']}")
        args = [case_literal(value, kind, f"{label} parameter {name}") for value, (name, kind)
                in zip(row["args"], params)]
        named = ", ".join(f"{name}={value}" for (name, _), value in zip(params, args))
        expected = case_literal(row["expected"], fn["result"], f"{label} expected result")
        cases.append(Case(name, fn["result"], args, f"{name}({named})", expected))
    return cases


def check_cases(binary, preview, work, cases):
    if not cases:
        return
    trial = work / "case.gpp"
    trial.write_bytes(preview)
    dump = checked(binary, "ast", trial)
    # Preserve every original function, including calls to main. In a private
    # copy of the compiler's comment-free AST dump, rename only the function
    # declaration and calls (local identifiers cannot be called in this profile).
    old_entry = "__original_main"
    names = set(re.findall(r"[A-Za-z_][A-Za-z_0-9]*", dump))
    while old_entry in names:
        old_entry += "_"
    module = re.sub(r"\bmain(?=\()", old_entry, dump)
    for index, case in enumerate(cases, 1):
        name = old_entry if case.function == "main" else case.function
        expected = case.expected
        call = f"{name}({', '.join(case.args)})"
        if case.result_type == "Bool":
            body = f"if {call} {{ return 1; }} return 0;"
        elif case.result_type == "Unit":
            body = f"{call}; return 0;"
        else:
            body = f"return {call};"
        trial.write_text(f"{module}\npub fn main() -> I64 !{{}} {{ {body} }}\n", encoding="utf-8")
        result = compiler(binary, "run", "--interpreter", "--fuel", "1000000", trial)
        context = f"Case {index}: {case.named}"
        if result.returncode:
            detail = result.stderr.decode(errors="replace").strip()
            if not detail.startswith("fault:"):
                raise ProposalError(f"Case harness failed: {detail}")
            raise CaseFailure(case, f"{context} raised {detail}; expected {expected}.",
                              f"{case.call()} failed during execution. {detail}")
        actual = result.stdout.decode().strip()
        if case.result_type == "Bool":
            if actual not in ("0", "1"):
                raise ProposalError(f"Unexpected Boolean encoding from the interpreter: {actual!r}")
            actual = {"1": "true", "0": "false"}[actual]
        elif case.result_type == "Unit":
            actual = "()"
        if actual != expected:
            raise CaseFailure(case, f"{context} returned {actual}; expected {expected}.",
                              f"{case.call()} returned {actual}. Expected {expected}.")


def checked_proposal(binary, apply, base, form, function, content, work):
    draft = work / "draft.gpp"
    draft.write_text(content, encoding="utf-8")
    preview = compiler(*apply, draft, "--expect", base, "--stdout")
    if preview.returncode:
        error = preview.stderr.decode(errors="replace").strip()
        if "error[GPP-" in error:
            raise ValueError(error)
        raise ProposalError(error)
    canonical = canonical_fragment(binary, preview.stdout, work, function, form)
    if canonical != content:
        draft.write_text(canonical, encoding="utf-8")
        preview = compiler(*apply, draft, "--expect", base, "--stdout")
        if preview.returncode:
            raise ProposalError(preview.stderr.decode(errors="replace").strip())
    return canonical, preview.stdout


def publish(output, content):
    # Publish a completed file atomically while refusing to replace any path
    # that appeared after the initial check, including symlinks and the source.
    with tempfile.NamedTemporaryFile(dir=output.parent) as stage:
        stage.write(content.encode())
        stage.flush()
        os.fsync(stage.fileno())
        os.link(stage.name, output)


def propose(args):
    if os.path.lexists(args.output):
        raise ProposalError(f"Output already exists: {args.output}")
    if not args.output.parent.is_dir():
        raise ProposalError(f"Output directory does not exist: {args.output.parent}")
    if not args.task.strip():
        raise ProposalError("Supply a nonempty task description.")
    binary = shutil.which(args.gpp)
    if not binary:
        raise ProposalError("Cannot find gpp. Build it with cargo build or pass --gpp PATH.")
    source = args.file.read_bytes()
    with tempfile.TemporaryDirectory(prefix="gpp-proposal-") as scratch:
        snapshot = Path(scratch) / "base.gpp"
        snapshot.write_bytes(source)
        base = checked(binary, "revision", snapshot).strip()
        checked(binary, "check", snapshot)
        dump = checked(binary, "ast", snapshot)
        fn, other = target_context(dump, args.function)
        declarations = {f["name"]: f for f in FUNCTION.finditer(dump)}
        cases = load_cases(args.cases, args.function, declarations)
        protected_body = textwrap.indent(textwrap.dedent(fn["body"]).strip(), "    ") if args.prepend else None
        available = [] if args.caller_context_on_failure else other
        original, prefix, params = generation_context(fn, available, args, cases)
        if args.caller_context:
            original += caller_section(declarations, args.function)
        if cases and not args.maintenance:
            original += "\nExamples:\n" + "\n".join(f"{c.named} gives {c.expected}." for c in cases[:3])
        model, template, model_parameters, digest = local_model(args.model, args.port, args.maintenance)
        raw_fim = args.maintenance and digest == STAR_FIM_DIGEST
        if args.infill and not raw_fim and not re.search(r"\{\{[^{}]*\.Suffix\b[^{}]*\}\}", template):
            hint = f" Try a local FIM model such as {MAINTENANCE_MODEL}." if args.maintenance else ""
            raise ProposalError(f"Model {model!r} has no .Suffix infill template." + hint)
        stops = generation_stops(model_parameters, args.surface, STAR_STOPS if raw_fim else ()) if (
            args.stop_at_boundary or (args.surface == "policy" and args.infill)) else None
        prompt = original
        apply = [binary, "edit", str(args.file), "--function", args.function, "--" + args.form]
        max_attempts = 1 if args.attempts == "1" else 2
        for attempt in range(max_attempts):
            raw = complete(model, template, prefix, prompt, args, stops, retry=bool(attempt),
                           raw_fim=raw_fim, protected_body=protected_body)
            try:
                if args.surface == "policy":
                    rules = POLICY_PREFIX + raw + POLICY_SUFFIX if args.infill else raw
                    content = lower_policy(rules, params, SCALAR_TYPES[fn["result"]], original_body=fn["body"]) + "\n"
                elif args.surface == "python":
                    content = projected_fragment(raw, args.form, params)
                else:
                    content = fragment(raw if protected_body is None else raw.rstrip() + "\n" + protected_body,
                                       args.form)
                canonical, preview = checked_proposal(
                    binary, apply, base, args.form, args.function, content, Path(scratch)
                )
                # A trailing "else" can consume the first protected "if" and still
                # make a valid module. Require the canonical top-level statements
                # to end with the original statement list before publishing.
                if protected_body and not ("\n" + canonical).endswith("\n" + textwrap.dedent(protected_body) + "\n"):
                    raise ValueError("Insertion crossed the protected original statement boundary.")
                check_cases(binary, preview, Path(scratch), cases)
            except ValueError as exc:
                feedback = str(exc)
                caller_failure = (args.caller_context_on_failure and isinstance(exc, CaseFailure)
                                  and is_caller(declarations, exc.function, args.function))
                if attempt + 1 == max_attempts or (args.attempts == "caller" and not caller_failure):
                    msg = ("Neither completion passed validation" if attempt else "Completion failed validation")
                    raise ProposalError(msg + ". Last diagnostic:\n" + feedback) from exc
                extra = ""
                if caller_failure:
                    obligation = None
                    if args.caller_obligation and exc.case.result_type == "I64":
                        obligation = public_obligation(args.caller_obligation, snapshot, exc.function,
                                                       args.function, exc.case.args, exc.case.expected)
                    extra = ("\n" + obligation_text(obligation) if obligation
                             else caller_section(declarations, args.function))
                if args.maintenance:
                    prompt = maintenance_context(fn, args.task, cases, args.prepend, [
                        "Previous insertion", raw, exc.compact[:600], extra.strip()])
                else:
                    prompt = original + extra + "\nPrevious completion:\n" + raw + "\nValidation feedback:\n" \
                        + feedback[:600] + "\nComplete the function again."
                continue
            if cases and checked(binary, "revision", args.file).strip() != base:
                raise ProposalError("stale revision: source changed during example validation")
            publish(args.output, canonical)
            diff = difflib.unified_diff(source.decode().splitlines(), preview.decode().splitlines(),
                                        fromfile=str(args.file), tofile="checked proposal", lineterm="")
            print("\n".join(diff))
            if cases:
                print(f"\nPassed {len(cases)} supplied cases.")
            print(f"\nFragment: {args.output}\nBase revision: {base}")
            print("Apply after review:\n" + shlex.join([*apply, str(args.output), "--expect", base]))
            return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path, help="checked scalar GPT++ source")
    parser.add_argument("--function", required=True)
    parser.add_argument("--task", required=True, help="desired behavior or maintenance change")
    parser.add_argument("--model", help=f"installed local model (maintenance default: {MAINTENANCE_MODEL})")
    form = parser.add_mutually_exclusive_group(required=True)
    form.add_argument("--expr", dest="form", action="store_const", const="expr",
                      help="replace the body with one return expression")
    form.add_argument("--body", dest="form", action="store_const", const="body",
                      help="replace the statement list")
    form.add_argument("--maintenance", dest="form", action="store_const", const="maintenance",
                      help="experimental native full-body infill with public cases and a caller-triggered retry")
    parser.add_argument("--prepend", action="store_true",
                        help="with --maintenance, insert statements above the protected original body")
    context = parser.add_mutually_exclusive_group()
    context.add_argument("--caller-context", action="store_true", help="include bounded excerpts of checked callers")
    context.add_argument("--caller-context-on-failure", action="store_true",
                         help="include caller excerpts only when retrying a failed example for a direct or transitive caller")
    context.add_argument("--caller-obligation", metavar="PROGRAM",
                         help="retry a failed caller with a compiler-derived target result when available")
    parser.add_argument("--cases", type=Path, help="JSON examples with positional args and an expected scalar result")
    parser.add_argument("--infill", action="store_true", help="use the installed model's native suffix template")
    parser.add_argument("--stop-at-boundary", action="store_true",
                        help="add model-side stop sequences for the infill gap")
    parser.add_argument("--surface", choices=("gpp", "python", "policy"), default="gpp",
                        help="proposal syntax (python requires --infill; policy requires --body)")
    parser.add_argument("--attempts", choices=("1", "2", "caller"),
                        help="one shot, up to two attempts, or retry only on a failed checked caller case")
    parser.add_argument("-o", "--output", required=True, type=Path, help="new fragment file")
    built = ROOT / "target/debug/gpp"
    parser.add_argument("--gpp", default=str(built) if built.is_file() else "gpp")
    parser.add_argument("--port", type=int, default=11434, help="local Ollama port (default 11434)")
    args = parser.parse_args()
    args.maintenance = args.form == "maintenance"
    if args.maintenance:
        if not args.cases:
            parser.error("--maintenance requires --cases FILE with at least one public example")
        if args.surface != "gpp" or args.caller_context:
            parser.error("--maintenance uses native GPT++ and a target-only first prompt")
        args.form, args.infill, args.stop_at_boundary = "body", True, True
        args.model = args.model or MAINTENANCE_MODEL
        args.attempts = "1" if args.attempts == "1" else "caller"
    else:
        if args.prepend:
            parser.error("--prepend requires --maintenance")
        if not args.model:
            parser.error("the following arguments are required: --model")
        args.attempts = args.attempts or "2"
    if args.stop_at_boundary and not args.infill:
        parser.error("--stop-at-boundary requires --infill")
    if args.surface == "python" and not args.infill:
        parser.error("--surface python requires --infill")
    if args.surface == "policy" and args.form != "body":
        parser.error("--surface policy requires --body")
    if args.caller_obligation:
        if args.attempts == "1":
            parser.error("--caller-obligation requires a retry")
        helper = shutil.which(args.caller_obligation)
        if not helper:
            parser.error("caller analysis program could not be found")
        args.caller_obligation = helper
        args.attempts = "caller"
    if args.attempts == "caller":
        if args.caller_context or not args.cases:
            parser.error("--attempts caller requires --cases and a target-only first prompt (omit --caller-context)")
        args.caller_context_on_failure = True
    if args.caller_context_on_failure and args.attempts == "1":
        parser.error("--caller-context-on-failure requires a second attempt")
    if not 1 <= args.port <= 65535:
        parser.error("port must be in 1..65535")
    try:
        propose(args)
    except (ProposalError, OSError, UnicodeError, ValueError, RecursionError, http.client.HTTPException,
            subprocess.TimeoutExpired) as exc:
        parser.exit(1, f"propose: {exc}\n")


if __name__ == "__main__":
    main()
