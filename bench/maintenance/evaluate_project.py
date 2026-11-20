"""Scoped multi-function patching and execution for the maintenance benchmark."""

import ast
from dataclasses import dataclass
from pathlib import Path
import re
from tempfile import TemporaryDirectory

from evaluate import arguments
from fragments import _brace_fragment, _brace_tokens
from scalar_builtins import lower_fragment


MODULE = "module benchmark.maintenance;\n\n"
ENTRY = "\npub fn main() -> I64 !{} { return 0; }\n"
HEADER = re.compile(r"^(?:pub )?fn (?P<name>[A-Za-z_][A-Za-z_0-9]*)\(")


@dataclass(frozen=True)
class Function:
    name: str
    signature: str
    body: str
    start: int
    end: int

    def record(self):
        return {"name": self.name, "signature": self.signature, "body": self.body}


def python_functions(source):
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    for fn in tree.body:
        if not isinstance(fn, ast.FunctionDef) or fn.decorator_list:
            raise ValueError("Expected ordinary top-level Python functions.")
        # The editable declaration occupies one line in the fixture format.
        signature = lines[fn.lineno - 1].rstrip()
        if not signature.endswith(":") or fn.body[0].lineno <= fn.lineno:
            raise ValueError("Expected a one-line typed declaration and a separate function body.")
        yield Function(fn.name, signature, "".join(lines[fn.lineno:fn.end_lineno]),
                       offsets[fn.lineno - 1], offsets[fn.end_lineno])


def braced_functions(source):
    tokens = list(_brace_tokens(source))
    index = 0
    while index < len(tokens):
        start = tokens[index][1]
        match = HEADER.match(source[start:])
        if not match:
            raise ValueError(f"Unexpected text outside a function at byte {start}.")
        while tokens[index][0] != "{":
            index += 1
        if index and tokens[index - 1][0] == "!":
            if [t[0] for t in tokens[index:index + 3]] != ["{", "}", "{"]:
                raise ValueError("Expected an empty effect set followed by a body.")
            index += 2
        opening = tokens[index][1]
        depth = 1
        index += 1
        while index < len(tokens) and depth:
            token, close, end = tokens[index]
            depth += (token == "{") - (token == "}")
            index += 1
        if depth:
            raise ValueError("Unclosed function body.")
        yield Function(match["name"], source[start:opening].rstrip(), source[opening + 1:close], start, end)


def functions(source, language):
    try:
        items = list(python_functions(source) if language == "python" else braced_functions(source))
    except (IndexError, SyntaxError) as exc:
        raise ValueError(f"Invalid module: {exc}") from exc
    result = {fn.name: fn for fn in items}
    if len(result) != len(items):
        raise ValueError("Duplicate function names in the module.")
    return result


def source_for(task, language, variant="starter"):
    return task[variant][language].strip() + "\n\n" + task["callers"][language].strip() + "\n"


def target_parts(task, language, source, raw, surface):
    name = task["target"]
    form = task["form"]
    if surface == "python":
        if language == "python":
            signature = functions(source, language)[name].signature
        else:
            signature = projection_signature(task)
        cleaned = raw[4:] if form == "body" and raw.startswith("    ") else raw
        patched = signature + "\n    " + ("return " if form == "expr" else "") + cleaned.rstrip() + "\n"
        tree = ast.parse(patched)
        if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
            raise ValueError("Completion crossed the editable function boundary.")
        fn = tree.body[0]
        if form == "expr" and (len(fn.body) != 1 or not isinstance(fn.body[0], ast.Return)
                               or fn.body[0].value is None):
            raise ValueError("Supply exactly one expression.")
        # The benchmark edits pure functions. Prevent a generated body from replacing
        # other module definitions at runtime or introducing standalone helper scopes.
        blocked = (ast.Global, ast.Nonlocal, ast.Import, ast.ImportFrom,
                   ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        external_state = {"globals", "locals", "exec", "eval", "compile", "open", "__import__", "setattr",
                          "delattr", "print", "breakpoint", "input", "getattr", "vars"}
        for statement in fn.body:
            for node in ast.walk(statement):
                if (isinstance(node, blocked)
                        or isinstance(node, ast.Name) and node.id in external_state
                        or isinstance(node, ast.Attribute) and node.attr.startswith("__")):
                    raise ValueError("Use a pure scalar function body with local values and normal calls.")
        compile(tree, "<patch>", "exec")
        if language == "python":
            return patched, None
        scalars = ast.unparse(fn.body[0].value) if form == "expr" else "\n".join(map(ast.unparse, fn.body))
        return None, lower_fragment(scalars, form, task["params"])
    return None, _brace_fragment(raw, form == "expr")


def projection_signature(task):
    parameters = ", ".join(f"{name}: {kind}" for name, kind in task["params"])
    return f"def {task['target']}({parameters}) -> int:"


def materialize(tools, task, language, surface, source, raw):
    try:
        patched, fragment = target_parts(task, language, source, raw, surface)
        target = functions(source, language)[task["target"]]
        name = target.name
        if language == "gpp":
            with TemporaryDirectory(prefix="caller-edit-") as directory:
                work = Path(directory).resolve()
                file = work / "base.gpp"
                edit = work / "fragment.gpp"
                file.write_text(MODULE + source + ENTRY)
                edit.write_text(fragment)
                code, out, error = tools.run([tools.gpp, "edit", file, "--function", name,
                                              "--" + task["form"], edit, "--stdout"], work)
                if code:
                    return "check_error", detail(work, code, out, error), ""
            before = MODULE + source[:target.start]
            after = source[target.end:] + ENTRY
            if not out.startswith(before) or not out.endswith(after):
                raise RuntimeError("GPT++ edit changed source outside the selected function.")
            full = out[len(MODULE):-len(ENTRY)]
        else:
            if language == "rust":
                statement = ("return " + fragment.rstrip() + "\n;") if task["form"] == "expr" else fragment
                patched = target.signature + " {\n    " + statement.rstrip() + "\n}"
            full = source[:target.start] + patched.rstrip() + source[target.end:]
            if language == "python":
                full = source[:target.start] + patched + source[target.end:]
        updated = functions(full, language)
        if (updated.keys() != functions(source, language).keys()
                or updated[name].signature != target.signature):
            raise RuntimeError("Scoped edit changed the function roster or signature.")
        return "pass", "", full
    except (SyntaxError, ValueError, RecursionError) as exc:
        return "check_error", str(exc)[:600], ""


def detail(work, code, output, error):
    return (error or output or f"Process exited with status {code}.").replace(str(work) + "/", "").strip()[:600]


def evaluate(tools, language, source, examples, *, already_checked=False):
    """Check and call the unchanged consumers against a public or hidden set."""
    with TemporaryDirectory(prefix="caller-eval-") as directory:
        work = Path(directory).resolve()
        calls = [f"{fn}({arguments(args, language)})" for fn, args, _ in examples]
        if language == "gpp":
            trial = work / "trial.gpp"
            # Batch independent scalar checks in one interpreter invocation. Return
            # the first failing row, then rerun that row to get its actual output.
            check = "\n".join(f"    if {call} != {expected} {{ return {i}; }}"
                              for i, (call, (_, _, expected)) in enumerate(zip(calls, examples), 1))
            trial.write_text(MODULE + source + f"\npub fn main() -> I64 !{{}} {{\n{check}\n    return 0;\n}}\n")
            code, out, error = tools.run([tools.gpp, "run", "--interpreter", "--fuel", "10000000", trial], work)
            if code:
                status = "check_error" if "error[GPP-" in error else "runtime_error"
                return status, detail(work, code, out, error)
            row = int(out.strip())
            if row == 0:
                return "pass", ""
            if not 1 <= row <= len(examples):
                raise RuntimeError("Unexpected integration harness result.")
            trial.write_text(MODULE + source + f"\npub fn main() -> I64 !{{}} {{ return {calls[row - 1]}; }}\n")
            code, out, error = tools.run([tools.gpp, "run", "--interpreter", trial], work)
            if code:
                return "runtime_error", detail(work, code, out, error)
            return mismatch(calls[row - 1], out.strip(), examples[row - 1][2])
        if language == "rust":
            trial = work / "trial.rs"
            exe = work / "test_program"
            lines = [f'    println!("{{}}", {call});' for call in calls]
            trial.write_text(source + "\nfn main() {\n" + "\n".join(lines) + "\n}\n")
            code, out, error = tools.run(
                [tools.rustc, "--edition=2024", "-C", "overflow-checks=yes", trial, "-o", exe],
                work, compile_step=True,
            )
            if code:
                return "check_error", detail(work, code, out, error)
            code, out, error = tools.run([exe], work)
        else:
            trial = work / "trial.py"
            emits = "\n".join(f"benchmark_emit({call})" for call in calls)
            trial.write_text(source + "\ndef benchmark_emit(value: int) -> None:\n"
                             "    if type(value) is not int:\n        raise TypeError('expected int')\n"
                             f"    print(value)\n\n{emits}\n")
            if not already_checked:
                config = work / "mypy.ini"
                config.write_text("[mypy]\n")
                code, out, error = tools.run(
                    [tools.python, "-I", "-m", "mypy", "--strict", "--no-site-packages",
                     "--cache-dir=/dev/null", "--config-file", config, trial], work, compile_step=True,
                )
                if code:
                    return "check_error", detail(work, code, out, error)
            code, out, error = tools.run([tools.python, "-I", trial], work)
        if code:
            return "runtime_error", detail(work, code, out, error)
        lines = out.splitlines()
        if len(lines) != len(calls):
            return "wrong_answer", f"Expected {len(calls)} values, received {len(lines)}."
        for call, output, (_, _, expected) in zip(calls, lines, examples):
            if output != str(expected):
                return mismatch(call, output, expected)
        return "pass", ""


def mismatch(call, actual, expected):
    return "wrong_answer", f"{call} returned {actual[:60]}. Expected {expected}."
