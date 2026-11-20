"""Native language renderers and execution adapters for the frozen transition tasks."""

from dataclasses import dataclass
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess


LANGUAGES = ("gpp", "rust", "python")
HOLE = "change"


def literal(lang, v):
    if isinstance(v, bool):
        return str(v) if lang == "python" else str(v).lower()
    return str(v)


def expr(lang, raw):
    if raw.startswith("bit("):
        b = raw[4:-1]
        return {"gpp": f"(({b}) as I64)", "rust": f"(({b}) as i64)", "python": f"int({b})"}[lang]
    if "bit(" in raw:
        before, rest = raw.split("bit(", 1)
        return before + expr(lang, "bit(" + rest)
    return (
        raw.replace(" OR ", " or " if lang == "python" else " || ")
        .replace("true", literal(lang, True))
        .replace("false", literal(lang, False))
    )


def state(lang, task, values):
    if lang == "rust":
        return "State { " + ", ".join(f"{n}: {v}" for (n, _), v in zip(task.fields, values)) + " }"
    return "State(" + ", ".join(values) + ")"


def source(lang, task, fill=None):
    """Full native declarations and protected transition. A pending slot is marked in each language."""
    kind = {
        "gpp": task.result_type,
        "rust": "i64" if task.result_type == "I64" else "bool",
        "python": "int" if task.result_type == "I64" else "bool",
    }[lang]
    hole = f"?{HOLE}: {kind}" if fill is None else "(" + fill + ")"
    if lang == "gpp":
        fields = ", ".join(f"{n}: {t}" for n, t in task.fields)
        lines = [
            "module study.transition;",
            f"enum Event {{ {', '.join(task.actions)} }}",
            f"record State {{ {fields} }}",
            "fn step(s: State, e: Event) -> State !{} {",
        ]
    elif lang == "rust":
        fields = ", ".join(f"{n}: {'i64' if t == 'I64' else 'bool'}" for n, t in task.fields)
        lines = [
            "use std::cmp::{min, max};",
            "#[derive(Clone, Copy, PartialEq)]",
            f"enum Event {{ {', '.join(task.actions)} }}",
            "#[derive(Clone, Copy)]",
            f"struct State {{ {fields} }}",
            "fn step(s: State, e: Event) -> State {",
        ]
    else:
        lines = [
            "from dataclasses import dataclass",
            "from enum import Enum",
            "",
            "class Event(Enum):",
            *(f"    {e} = {i}" for i, e in enumerate(task.actions)),
            "",
            "@dataclass(frozen=True)",
            "class State:",
            *(f"    {n}: {'int' if t == 'I64' else 'bool'}" for n, t in task.fields),
            "",
            "def step(s: State, e: Event) -> State:",
        ]
    for i, (action, branch) in enumerate(zip(task.actions, task.branches, strict=True)):
        value = state(lang, task, [hole if e == "?" else expr(lang, e) for e in branch])
        if lang == "python":
            if i + 1 < len(task.actions):
                lines.extend([f"    if e == Event.{action}:", f"        return {value}"])
            else:
                lines.append("    return " + value)
        elif i + 1 < len(task.actions):
            lines.append(f"    if e == Event::{action} {{ return {value}; }}")
        else:
            lines.append(f"    return {value};")
    if lang != "python":
        lines.append("}")
    return "\n".join(lines) + "\n"


def traces_gpp(task, traces, oracle):
    init = state("gpp", task, [literal("gpp", x) for x in task.initial])
    lines = []
    for i, trace in enumerate(traces):
        term = init
        for c in trace:
            term = f"step({term}, Event::{task.actions['ABC'.index(c)]})"
        pred = " && ".join(
            f"{term}.{n} == {literal('gpp', v)}" for (n, _), v in zip(task.fields, oracle(task, trace))
        )
        lines.append(f"contract visible_{i}() {{ {pred} }}")
    return "\n".join(lines) + "\n"


def gpp_program(task, fill, oracle):
    return (
        source("gpp", task, fill)
        + "pub fn main() -> I64 !{} { return 0; }\n"
        + traces_gpp(task, task.public, oracle)
    )


def command(argv, *, stdin=None, cwd=None, timeout=40):
    return subprocess.run(
        [str(x) for x in argv], input=stdin, cwd=cwd, capture_output=True, text=True, timeout=timeout
    )


def checked(argv, **kwargs):
    p = command(argv, **kwargs)
    if p.returncode:
        raise ValueError((p.stderr or p.stdout)[-1400:])
    return p.stdout


def same(a, b):
    return json.dumps(a, separators=(",", ":")) == json.dumps(b, separators=(",", ":"))


def authorize(raw, task, lang):
    """Keep model-written fragments in a pure local expression grammar before any host execution."""
    candidate = raw.strip()
    if not candidate or len(candidate) > 700 or not candidate.isascii():
        raise ValueError("Supply a single native scalar expression of at most 700 ASCII characters.")
    names = {
        "s",
        "if",
        "else",
        "int",
        "as",
        "I64",
        "i64",
        "min",
        "max",
        "true",
        "false",
        "True",
        "False",
        "and",
        "or",
        "not",
    }
    names.update(n for n, _ in task.fields)
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*|[0-9]+|==|!=|<=|>=|&&|\|\||//|[^\s]", candidate)
    ops = {
        "+",
        "-",
        "*",
        "/",
        "//",
        "%",
        "(",
        ")",
        "{",
        "}",
        ".",
        ",",
        "==",
        "!=",
        "<",
        "<=",
        ">",
        ">=",
        "&&",
        "||",
        "!",
    }
    for i, tok in enumerate(tokens):
        if tok not in names and tok not in ops and not (tok.isdigit() and len(tok) <= 19):
            raise ValueError(f"Unsupported expression token {tok!r}.")
        if tok == "." and (
            i == 0 or tokens[i - 1] != "s" or i + 1 == len(tokens) or tokens[i + 1] not in dict(task.fields)
        ):
            raise ValueError("Only declared fields of state s are accessible.")
        if (
            tok in names
            and i + 1 < len(tokens)
            and tokens[i + 1] == "("
            and tok not in {"if", "else", "not", "and", "or", "min", "max", "int"}
        ):
            raise ValueError("Only the supplied scalar helpers may be called.")
    if lang == "python":
        tree = ast.parse(candidate, mode="eval")
        allowed = (
            ast.Expression,
            ast.Name,
            ast.Attribute,
            ast.Constant,
            ast.BoolOp,
            ast.BinOp,
            ast.Compare,
            ast.UnaryOp,
            ast.Call,
            ast.IfExp,
            ast.Load,
            ast.And,
            ast.Or,
            ast.Add,
            ast.Sub,
            ast.Mult,
            ast.FloorDiv,
            ast.Mod,
            ast.Not,
            ast.UAdd,
            ast.USub,
            ast.Eq,
            ast.NotEq,
            ast.Lt,
            ast.LtE,
            ast.Gt,
            ast.GtE,
        )
        if any(not isinstance(n, allowed) for n in ast.walk(tree)):
            raise ValueError("Unsupported node in the scalar expression.")
        for n in ast.walk(tree):
            if isinstance(n, ast.Call) and not (
                isinstance(n.func, ast.Name) and n.func.id in {"min", "max", "int"}
            ):
                raise ValueError("Only min, max and int may be called.")
    return candidate


def guide(lang):
    return {
        "gpp": "Select with if flag { yes } else { no }. Use &&, ||, !, min(a,b), max(a,b), and flag as I64.",
        "rust": "Select with if flag { yes } else { no }. Use &&, ||, !, min(a,b), max(a,b), and flag as i64.",
        "python": "Select with yes if flag else no. Use and, or, not, min(a,b), max(a,b), and int(flag).",
    }[lang]


def grammar(task):
    fields = [("field", "s." + n) for n, t in task.fields if t == task.result_type]
    if task.result_type == "Bool":
        leaves = fields + [("bool", "false"), ("bool", "true")]
        yield from leaves
        for leaf in leaves:
            yield ("not", leaf)
        for a in leaves:
            for b in leaves:
                for op in ("!=", "==", "and", "or"):
                    yield (op, a, b)
        return
    leaves = fields + [("int", str(n)) for n in (0, 1, 2)]
    yield from leaves
    for a in leaves:
        for b in leaves:
            for op in ("+", "-", "%", "min", "max"):
                yield (op, a, b)


def show(node, lang):
    op, *rest = node
    if op in ("field", "int"):
        return rest[0]
    if op == "bool":
        return literal(lang, rest[0] == "true")
    a = show(rest[0], lang)
    if op == "not":
        return f"(not {a})" if lang == "python" else f"!({a})"
    b = show(rest[1], lang)
    if op in ("min", "max"):
        return f"{op}({a}, {b})"
    sym = {"and": "&&", "or": "||"}.get(op, op) if lang != "python" else op
    return f"({a} {sym} {b})"


def observer_gpp(task):
    init = state("gpp", task, [literal("gpp", x) for x in task.initial])
    a, b, c = task.actions
    return f"""
fn bench_marker() -> I64 !{{}} {{ return 0; }}
fn observe(encoded: I64, length: I64, field: I64) -> I64 !{{}} {{
    var state = {init};
    var code = encoded;
    var left = length;
    while left > 0 {{
        let digit = code % 3;
        let event = if digit == 0 {{ Event::{a} }} else {{ if digit == 1 {{ Event::{b} }} else {{ Event::{c} }} }};
        state = step(state, event);
        code = code / 3;
        left = left - 1;
    }}
    return if field == 0 {{ state.{task.fields[0][0]} as I64 }} else {{ state.{task.fields[1][0]} as I64 }};
}}
"""


def py_observer(task):
    vals = ", ".join(literal("python", x) for x in task.initial)
    names = ", ".join("s." + n for n, _ in task.fields)
    return f"""
import sys
import json
for trace in sys.stdin:
    s = State({vals})
    try:
        for e in trace.strip():
            s = step(s, list(Event)["ABC".index(e)])
        print(json.dumps([{names}]))
    except ArithmeticError:
        print("null")
"""


def rs_observer(task):
    init = state("rust", task, [literal("rust", x) for x in task.initial])
    a, b, c = task.actions
    return f"""
use std::io::{{self, BufRead}};
fn main() {{
    std::panic::set_hook(Box::new(|_| {{}}));
    for line in io::stdin().lock().lines() {{
        let line = line.unwrap();
        let result = std::panic::catch_unwind(|| {{
            let mut s = {init};
            for c in line.bytes() {{
                s = step(s, match c {{ b'A' => Event::{a}, b'B' => Event::{b}, _ => Event::{c} }});
            }}
            s
        }});
        match result {{
            Ok(s) => println!("[{{}},{{}}]", s.{task.fields[0][0]},s.{task.fields[1][0]}),
            Err(_) => println!("null")
        }}
    }}
}}
"""


@dataclass
class Adapter:
    lang: str
    task: object
    work: Path
    binary: Path
    python: Path
    oracle: object

    def __post_init__(self):
        self.work.mkdir(parents=True, exist_ok=True)
        self.file = (
            self.work / {"gpp": "source.gpp", "rust": "candidate.rs", "python": "candidate.py"}[self.lang]
        )
        self.fragment = self.work / "fill.expr"
        self.executable = self.work / "candidate-exe"
        self.prepared = None
        if self.lang == "gpp":
            self.file.write_text(gpp_program(self.task, None, self.oracle))

    def fill(self, raw):
        """Check, apply and validate public inputs only; hold onto the final native executable."""
        self.prepared = None
        try:
            code = authorize(raw, self.task, self.lang)
        except (SyntaxError, ValueError) as exc:
            return "invalid_expression", str(exc)[:600]
        if self.lang == "gpp":
            self.fragment.write_text(code + "\n")
            p = command(
                [self.binary, "complete", self.file, "--hole", HOLE, "--fill", self.fragment, "--stdout"]
            )
            if p.returncode:
                # Normalize public failure details by evaluating only public calls with this insertion.
                tmp = self.work / "public-preview.gpp"
                tmp.write_text(gpp_program(self.task, code, self.oracle) + observer_gpp(self.task))
                check = command([self.binary, "check", tmp])
                if check.returncode:
                    return "check_error", self.clean(check.stderr)
                if p.returncode == 3:
                    return "incomplete", self.clean(p.stderr)
                self.prepared = tmp
                failure = self.public_check()
                self.prepared = None
                if failure[0] == "pass":
                    raise ValueError(
                        "GPT++ refused a type- and public-valid supplied expression: " + p.stderr[:700]
                    )
                return failure
            self.prepared = self.work / "checked.gpp"
            self.prepared.write_text(p.stdout + observer_gpp(self.task))
        elif self.lang == "rust":
            self.file.write_text(source(self.lang, self.task, code) + rs_observer(self.task))
            p = command(
                [
                    "rustc",
                    "--edition=2024",
                    "-A",
                    "warnings",
                    "-C",
                    "overflow-checks=yes",
                    self.file,
                    "-o",
                    self.executable,
                ]
            )
            if p.returncode:
                return "check_error", self.clean(p.stderr)
            self.prepared = self.executable
        else:
            self.file.write_text(source(self.lang, self.task, code))
            p = command(
                [
                    self.python,
                    "-m",
                    "mypy",
                    "--strict",
                    "--no-error-summary",
                    "--cache-dir",
                    self.work / "mypy",
                    self.file,
                ],
                cwd=self.work,
            )
            if p.returncode:
                return "check_error", self.clean(p.stdout or p.stderr)
            with self.file.open("a") as out:
                out.write(py_observer(self.task))
            self.prepared = self.file
        return self.public_check()

    def clean(self, text):
        return text.replace(str(self.work) + "/", "").strip()[:600]

    def public_check(self):
        values = self.observe(self.task.public)
        for trace, value in zip(self.task.public, values, strict=True):
            expected = list(self.oracle(self.task, trace))
            if not same(value, expected):
                return (
                    "public_failure",
                    f"After {describe(self.task, trace)} expected {expected}, observed {value}.",
                )
        return "pass", ""

    def observe(self, traces):
        if self.lang == "gpp":
            # The unmodified bench_marker is unrelated to state transitions. A no-op edit lets the
            # persistent native probe execute many scalar observer calls without changing the patch.
            text = self.prepared.read_bytes()
            marker = b"fn bench_marker() -> I64 !{} { return 0; }"
            a = text.index(marker) + marker.index(b"0;")
            rev = "sha256:" + hashlib.sha256(text).hexdigest()
            tape = self.work / "trace-inputs.tsv"
            rows = []
            for trace in traces:
                serial = sum("ABC".index(e) * 3**i for i, e in enumerate(trace))
                rows.extend(f"observe\t{serial}\t{len(trace)}\t{field}" for field in (0, 1))
            tape.write_text("\n".join(rows) + "\n")
            raw = checked(
                [
                    self.binary,
                    "probe",
                    self.prepared,
                    "--function",
                    "bench_marker",
                    "--expect",
                    rev,
                    "--cases",
                    tape,
                ],
                stdin=f"{a}:{a + 1} 1\n0",
            )
            hello, result = map(json.loads, raw.splitlines())
            if hello["revision"] != rev or result["status"] != "ok":
                raise ValueError(raw[:600])
            obs = result["outcomes"]
            if len(obs) != 2 * len(traces):
                raise ValueError("Missing trace observations")
            vals = []
            for i in range(0, len(obs), 2):
                pair = obs[i : i + 2]
                if any("fault" in v for v in pair):
                    vals.append(None)
                else:
                    vals.append(
                        [
                            bool(v["result"]) if field[1] == "Bool" else v["result"]
                            for v, field in zip(pair, self.task.fields)
                        ]
                    )
            return vals
        cmd = [self.prepared] if self.lang == "rust" else [self.python, "-I", self.prepared]
        raw = checked(cmd, stdin="\n".join(traces) + "\n")
        return [json.loads(line) for line in raw.splitlines()]


def describe(task, trace):
    return " → ".join(task.actions["ABC".index(c)] for c in trace)
