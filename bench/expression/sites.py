"""Checked expression ranges and patches in the three benchmark languages."""

import ast
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from evaluate_project import ENTRY, MODULE, functions, target_parts


def function_text(task, language, source):
    target = functions(source, language)[task["target"]]
    return source[target.start : target.end].rstrip("\n")


def python_ranges(text):
    # Python AST columns are UTF-8 byte offsets within each line.
    lines = [0]
    for line in text.encode().splitlines(keepends=True):
        lines.append(lines[-1] + len(line))
    return {
        (lines[n.lineno - 1] + n.col_offset, lines[n.end_lineno - 1] + n.end_col_offset)
        for stmt in ast.parse(text).body[0].body
        for n in ast.walk(stmt)
        if isinstance(n, ast.expr)
    }


def rust_syntax(binary, argument, text):
    proc = subprocess.run([binary, argument], input=text, capture_output=True, text=True, timeout=10)
    if proc.returncode:
        raise ValueError(proc.stderr.strip()[:600])
    return proc.stdout


def catalog(tools, rust_parser, task, language, source):
    """List byte ranges relative to the beginning of the target declaration."""
    text = function_text(task, language, source)
    if language == "python":
        return python_ranges(text)
    if language == "rust":
        return {
            tuple(map(int, line.split()))
            for line in rust_syntax(rust_parser, task["target"], text).splitlines()
        }
    with TemporaryDirectory() as directory:
        file = Path(directory) / "base.gpp"
        file.write_text(MODULE + source + ENTRY)
        listing = json.loads(
            subprocess.check_output([tools.gpp, "expressions", file, "--function", task["target"]], text=True)
        )
    start = listing["start_byte"]
    ranges = set()
    for entry in listing["expressions"]:
        a, b = entry["start_byte"] - start, entry["end_byte"] - start
        if text.encode()[a:b].decode() != entry["text"]:
            raise ValueError("Compiler expression offsets disagree with source")
        ranges.add((a, b))
    return ranges


def resolve(text, ranges, selection):
    old = selection.strip()
    if not old or len(old.splitlines()) != 1:
        raise ValueError("Selection must be one nonempty source line")
    source = text.encode()
    matches = [(a, b) for a, b in ranges if source[a:b] == old.encode()]
    if len(matches) != 1:
        raise ValueError(f"Selection matched {len(matches)} expression nodes")
    return matches[0]


def apply(tools, rust_parser, task, language, source, span, raw):
    """Validate a single expression, protect its grouping and preserve surrounding source."""
    target = functions(source, language)[task["target"]]
    a, b = span
    offset = len(source[: target.start].encode())
    old = source.encode()
    before, after = old[: offset + a], old[offset + b :]
    try:
        if language == "gpp":
            with TemporaryDirectory(prefix="expression-patch-") as directory:
                work = Path(directory).resolve()
                file, edit = work / "base.gpp", work / "fragment.gpp"
                file.write_text(MODULE + source + ENTRY)
                edit.write_text(raw)
                base = offset + len(MODULE.encode())
                code, out, err = tools.run(
                    [
                        tools.gpp,
                        "edit",
                        file,
                        "--function",
                        task["target"],
                        "--at",
                        f"{base + a}:{base + b}",
                        "--expr",
                        edit,
                        "--stdout",
                    ],
                    work,
                    compile_step=True,
                )
                if code:
                    return "check_error", (err or out).replace(str(work) + "/", "").strip()[:600], ""
                if not out.startswith(MODULE) or not out.endswith(ENTRY):
                    raise RuntimeError("Compiler changed the module envelope")
                result = out[len(MODULE) : -len(ENTRY)]
        else:
            fragment = raw.strip()
            if language == "python":
                ast.parse(fragment, mode="eval")
            else:
                rust_syntax(rust_parser, "--check", fragment)
            # A separated closing delimiter also protects the following source
            # when the last token of a valid expression is a line comment.
            result = (before + b"(" + fragment.encode() + b"\n)" + after).decode()
            if language == "python":
                body = functions(result, language)[task["target"]].body
                target_parts(dict(task, form="body"), language, result, body, language)
        if not result.encode().startswith(before) or not result.encode().endswith(after):
            raise RuntimeError("Patch changed bytes outside the selected expression")
        return "pass", "", result
    except (SyntaxError, ValueError, RecursionError) as exc:
        return "check_error", str(exc)[:600], ""
