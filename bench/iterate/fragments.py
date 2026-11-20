"""Apply a model's suffix to a fixed scalar function without changing its logic."""
import ast
from pathlib import Path
import re
import tempfile

from evaluate import signature


def prefix(task, language):
    opening = signature(task, language) + ("\n" if language == "python" else " {\n")
    return opening + ("    return " if task["form"] == "expr" else "    ")


def old_fragment(task, language):
    if "starter" not in task:
        return ""
    declaration = signature(task, language)
    source = task["starter"][language].rstrip()
    if not source.startswith(declaration):
        raise ValueError("Starter signature differs from the fixed declaration.")
    body = source[len(declaration):]
    if language != "python":
        block = body.strip()
        if not (block.startswith("{") and block.endswith("}")):
            raise ValueError("Expected a braced starter body.")
        body = block[1:-1]
    # The prefix already supplies indentation on the first line. Preserve
    # continuation-line indentation so prefix + suffix reconstructs the body.
    body = body.strip()
    if task["form"] == "expr":
        if body.startswith("return "):
            body = body[len("return "):]
        body = body.removesuffix(";").rstrip()
    return body


_RAW_STRING = re.compile(r'(?:br|cr|r)(#*)"')
_CHAR = re.compile(r"'(?:\\(?:x[0-9a-fA-F]{2}|u\{[0-9a-fA-F_]+\}|.)|[^\\'\n])'")


def _brace_tokens(text):
    """Find delimiter positions outside Rust comments and literal token trees."""
    i = 0
    while i < len(text):
        start = i
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if text.startswith("//", i):
            newline = text.find("\n", i + 2)
            i = len(text) if newline == -1 else newline + 1
            continue
        if text.startswith("/*", i):
            depth = 1
            i += 2
            while depth:
                if i >= len(text):
                    raise ValueError("Unclosed block comment.")
                if text.startswith("/*", i):
                    depth += 1
                    i += 2
                elif text.startswith("*/", i):
                    depth -= 1
                    i += 2
                else:
                    i += 1
            continue
        raw = _RAW_STRING.match(text, i) if ch in "bcr" else None
        char = _CHAR.match(text, i) if ch == "'" else None
        if raw:
            end = '"' + raw[1]
            close = text.find(end, raw.end())
            if close < 0:
                raise ValueError("Unclosed raw string.")
            i = close + len(end)
        elif char:
            i = char.end()
        elif ch == '"':
            i += 1
            while i < len(text) and text[i] != '"':
                i += 2 if text[i] == "\\" else 1
            if i >= len(text):
                raise ValueError("Unclosed string.")
            i += 1
        else:
            i += 1
            if ch.isalnum() or ch == "_":
                while i < len(text) and (text[i].isalnum() or text[i] == "_"):
                    i += 1
        yield text[start:i], start, i


def _brace_fragment(raw, expression):
    tokens = list(_brace_tokens(raw))
    removed = []
    delimiters = []
    closing = {"}": "{", ")": "(", "]": "["}
    for index, (token, start, end) in enumerate(tokens):
        if token in ("(", "{", "["):
            delimiters.append(token)
        elif token in closing:
            if delimiters and delimiters[-1] == closing[token]:
                delimiters.pop()
            elif token == "}" and not delimiters and index == len(tokens) - 1:
                removed.append((start, end))  # The optional prefilled function closer.
            else:
                raise ValueError("Completion closes a different scope or has code after the function.")
        elif token == ";" and expression and not delimiters:
            is_last = index == len(tokens) - 1
            before_closer = index == len(tokens) - 2 and tokens[-1][0] == "}"
            if not (is_last or before_closer):
                raise ValueError("The editable expression contains an additional statement.")
            removed.append((start, end))
    if delimiters:
        raise ValueError("Completion has an unclosed delimiter.")
    for start, end in reversed(removed):
        raw = raw[:start] + raw[end:]
    if not any(_brace_tokens(raw)):
        raise ValueError("Completion is empty.")
    return raw


def _python_function(task, raw):
    start = prefix(task, "python")
    code = start + raw.rstrip() + "\n"
    # A generator may spell the first line's indentation again. Normalize
    # that one margin only, retaining all later suites and explicit dedents.
    if task["form"] == "body" and raw.startswith("    "):
        code = start + raw[4:].rstrip() + "\n"
    tree = ast.parse(code)
    if len(tree.body) != 1 or not isinstance(tree.body[0], ast.FunctionDef):
        raise ValueError("Completion contains code outside the fixed function.")
    body = tree.body[0].body
    if task["form"] == "expr" and (
        len(body) != 1 or not isinstance(body[0], ast.Return) or body[0].value is None
    ):
        raise ValueError("Supply exactly one return expression.")
    # ast.parse alone permits constructs such as return or yield in invalid scopes.
    compile(tree, "<fragment>", "exec")
    return code


def _gpp_function(tools, task, fragment):
    heading = "module experiment.edit;\n"
    entry = "\npub fn main() -> I64 !{} { return 0; }\n"
    starter = task.get("starter", {}).get("gpp")
    if starter is None:
        starter = signature(task, "gpp") + " { return 0; }"
    with tempfile.TemporaryDirectory(prefix="gpp-fragment-") as folder:
        work = Path(folder).resolve()
        source = work / "base.gpp"
        field = work / "edit.gpp"
        source.write_text(heading + starter.rstrip() + entry)
        field.write_text(fragment)
        rc, out, err = tools.run([tools.gpp, "edit", source, "--function", "solve",
                                  "--" + task["form"], field, "--stdout"], work)
        if rc:
            detail = (err or out or f"gpp edit exited with status {rc}").replace(str(work) + "/", "")
            raise ValueError(detail.strip()[:600])
    if not out.startswith(heading) or not out.endswith(entry):
        raise RuntimeError("gpp edit changed the module or test entry.")
    code = out[len(heading):-len(entry)] + "\n"
    if not code.startswith(signature(task, "gpp")):
        raise RuntimeError("gpp edit changed the fixed signature.")
    return code


def edited_function(tools, task, language, raw_completion):
    try:
        if language == "python":
            result = _python_function(task, raw_completion)
        else:
            expr = task["form"] == "expr"
            fragment = _brace_fragment(raw_completion, expr)
            if language == "gpp":
                result = _gpp_function(tools, task, fragment)
            elif language == "rust":
                # Put the semicolon on its own line to keep a trailing line
                # comment from swallowing the supplied expression terminator.
                result = prefix(task, language) + fragment.rstrip() + ("\n;" if expr else "") + "\n}\n"
            else:
                raise ValueError("Unknown fragment language.")
    except (SyntaxError, ValueError, RecursionError) as error:
        return "check_error", str(error)[:600], ""
    return "pass", "", result
