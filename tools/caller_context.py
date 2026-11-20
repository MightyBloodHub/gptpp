"""Bounded reverse-call context for checked, single-module scalar function records.

Records contain name, signature and body (statements inside the declaration).
Only direct calls to known functions participate; dynamic dispatch and macro
expansion are outside these scalar language profiles.
"""
import ast
from bisect import bisect_right
import re
from textwrap import dedent


MAX_DEPTH = 2
MAX_CALLERS = 3
SIGNATURE_WIDTH = 144
LINE_WIDTH = 96
IDENT = re.compile(r"[A-Za-z_]\w*", re.ASCII)
# The Rust baseline can contain literals and nested block comments. Preserve
# line breaks and character positions when masking them for call lookup.
TOKEN = re.compile(
    r'//[^\r\n]*|/\*|(?:br|cr|r)(?P<hash>\#*)"|(?:b|c)?"(?:\\.|[^"\\])*"|'
    r"""b?'(?:\\(?:x[0-9a-fA-F]{2}|u\{[0-9a-fA-F_]+\}|.)|[^'\\\n])'""",
    re.S,
)


def _mask(text):
    masked = list(text)
    cursor = 0
    while match := TOKEN.search(text, cursor):
        end = match.end()
        if match[0] == "/*":
            depth = 1
            for delimiter in re.finditer(r"/\*|\*/", text[end:]):
                depth += 1 if delimiter[0] == "/*" else -1
                if not depth:
                    end += delimiter.end()
                    break
            else:
                end = len(text)
        elif match["hash"] is not None:
            close = '"' + match["hash"]
            at = text.find(close, end)
            end = len(text) if at < 0 else at + len(close)
        for i in range(match.start(), end):
            if masked[i] not in "\r\n":
                masked[i] = " "
        cursor = end
    return "".join(masked)


def _braced_calls(body, names, language):
    # In checked GPT++ the only body production with an identifier followed by
    # '(' is a direct call. Scan bodies only, never function signatures.
    masked = _mask(body)
    tokens = list(re.finditer(r"[A-Za-z_]\w*|::|[^\s]", masked, re.ASCII))
    starts = [0, *(match.end() for match in re.finditer("\n", masked))]
    shadowed = set()
    nested = set()
    if language == "rust":
        for i, token in enumerate(tokens):
            if token[0] in ("let", "fn") and i + 1 < len(tokens):
                j = i + 1
                if tokens[j][0] == "mut":
                    j += 1
                if j < len(tokens):
                    shadowed.add(tokens[j][0])
            if token[0] == "fn" and i + 1 < len(tokens) and IDENT.fullmatch(tokens[i + 1][0]):
                # A local fn owns its own calls. Scalar module records describe
                # top-level functions only, so omit that nested declaration.
                j = i + 1
                while j < len(tokens) and tokens[j][0] not in ("{", ";"):
                    j += 1
                end = j + 1
                if j < len(tokens) and tokens[j][0] == "{":
                    level = 1
                    while end < len(tokens) and level:
                        level += (tokens[end][0] == "{") - (tokens[end][0] == "}")
                        end += 1
                nested.update(range(i, end))
    for i, token in enumerate(tokens[:-1]):
        if i in nested or token[0] not in names or token[0] in shadowed or tokens[i + 1][0] != "(":
            continue
        if i and tokens[i - 1][0] in ("fn", ".", "::"):
            continue
        line = bisect_right(starts, token.start()) - 1
        col = token.start() - starts[line]
        yield token[0], line, col


def _python_calls(body, names):
    tree = ast.parse(body)
    rows = body.splitlines()
    calls = []
    shadowed = set()

    class Visit(ast.NodeVisitor):
        def visit_Call(self, node):
            if isinstance(node.func, ast.Name) and node.func.id in names:
                row = rows[node.lineno - 1]
                col = len(row.encode()[:node.col_offset].decode())
                calls.append((node.func.id, node.lineno - 1, col))
            self.generic_visit(node)

        def visit_Name(self, node):
            if isinstance(node.ctx, ast.Store):
                shadowed.add(node.id)

        def visit_FunctionDef(self, node):
            shadowed.add(node.name)

        visit_AsyncFunctionDef = visit_FunctionDef
        visit_ClassDef = visit_FunctionDef

        def visit_Lambda(self, node):
            pass

    Visit().visit(tree)
    return [call for call in calls if call[0] not in shadowed]


def _clip(line, width, column=0):
    if len(line) <= width:
        return line
    start = max(0, min(column - width // 3, len(line) - width + 2))
    return ("…" if start else "") + line[start:start + width - 2] + "…"


def _excerpt(body, line, column):
    rows = body.splitlines()
    excerpt = []
    for i in range(max(0, line - 1), min(len(rows), line + 2)):
        row = rows[i].rstrip()
        if row.strip() and not row.lstrip().startswith(("//", "#", "/*")):
            excerpt.append(_clip(row, LINE_WIDTH, column if i == line else 0))
    return "\n".join(excerpt)


def caller_context(functions, target, language):
    """Return read-only caller excerpts ordered by shortest reverse distance and name."""
    if language not in ("gpp", "rust", "python"):
        raise ValueError("expected gpp, rust or python caller records")
    records = {}
    for function in functions:
        name = function["name"]
        if not IDENT.fullmatch(name) or name in records:
            raise ValueError(f"invalid or duplicate function name {name!r}")
        records[name] = (function["signature"], dedent(function["body"]))
    if target not in records:
        raise ValueError(f"unknown target {target!r}")

    # Store the earliest direct callsite for each edge. In a diamond, show the
    # earliest source call to the preceding layer regardless of map iteration.
    reverse = {}
    for name, (_, body) in records.items():
        calls = _python_calls(body, records) if language == "python" else _braced_calls(body, records, language)
        for callee, line, column in calls:
            by_caller = reverse.setdefault(callee, {})
            by_caller[name] = min((line, column), by_caller.get(name, (line, column)))
    seen = {target}
    frontier = {target}
    contexts = []
    for _ in range(MAX_DEPTH):
        layer = {}
        for callee in frontier:
            for caller, (line, column) in reverse.get(callee, {}).items():
                if caller not in seen:
                    edge = (line, column, callee)
                    layer[caller] = min(edge, layer.get(caller, edge))
        for caller in sorted(layer):
            line, column, callee = layer[caller]
            signature, body = records[caller]
            contexts.append(f"{_clip(signature, SIGNATURE_WIDTH)}  [calls {_clip(callee, 48)}]\n" +
                            _excerpt(body, line, column))
            if len(contexts) == MAX_CALLERS:
                break
        if not layer or len(contexts) == MAX_CALLERS:
            break
        seen.update(layer)
        frontier = layer.keys()
    return "Read-only caller excerpts:\n" + "\n\n".join(contexts) if contexts else ""
