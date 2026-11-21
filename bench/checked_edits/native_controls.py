"""Native typed Python and Rust execution for the shared one-expression experiment."""

import ast
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from bench.search.engine import render
from bench.stateful.adapters import guide


class CandidateError(ValueError):
    """A proposed fragment is outside the edit scope or fails the native type checker."""


PREC = {"||": 1, "&&": 2, "==": 3, "!=": 3, "<": 4, ">": 4, "<=": 4, ">=": 4,
        "+": 5, "-": 5, "*": 6, "/": 6, "%": 6}
TOKEN = re.compile(r"[A-Za-z_][A-Za-z_0-9]*|[0-9]+|&&|\|\||==|!=|<=|>=|[^\s]")
ARITY = {"abs": 1, "min": 2, "max": 2, "clamp": 3}
PYTHON = ROOT / "target/empirical-venv/bin/python"
TYPES = {"rust": {"I64": "i64", "Bool": "bool"}, "python": {"I64": "int", "Bool": "bool"}}


def syntax_guide(language):
    return guide(language) + " abs(x) and clamp(x, lo, hi) are available."


def bounded(expression):
    if not isinstance(expression, str) or not expression.strip() or len(expression) > 700 or not expression.isascii():
        raise CandidateError("Supply one scalar expression of at most 700 ASCII characters.")
    return expression.strip()


class ScalarParser:
    """Render the scalar subset of GPT++ or check a Rust fragment before rustc sees it."""

    def __init__(self, expression, language, names=None, cast="I64"):
        self.tokens = TOKEN.findall(bounded(expression)) + [""]
        self.index = 0
        self.language = language
        self.names = names
        self.cast = cast

    def take(self, expected=None):
        token = self.tokens[self.index]
        if not token or expected is not None and token != expected:
            raise CandidateError(f"Expected {expected or 'an expression'}, found {token!r}")
        self.index += 1
        return token

    def group(self, start, stop):
        self.take(start)
        value = self.expression()
        self.take(stop)
        return value

    def atom(self):
        token = self.tokens[self.index]
        if token == "(":
            return self.group("(", ")")
        self.take()
        if token == "if":
            condition = self.expression()
            yes = self.group("{", "}")
            self.take("else")
            no = self.atom() if self.tokens[self.index] == "if" else self.group("{", "}")
            return render(("if", condition, yes, no), self.language)
        if token in ("!", "-"):
            value = self.atom()
            return f"(-{value})" if token == "-" else render(("not", value), self.language)
        if token in ARITY and self.tokens[self.index] == "(":
            self.take("(")
            args = [self.expression()]
            for _ in range(ARITY[token] - 1):
                self.take(",")
                args.append(self.expression())
            self.take(")")
            return f"{token}({', '.join(args)})"
        if token in ("true", "false"):
            return render(token == "true", self.language)
        if token.isdecimal() and len(token) <= 19:
            return str(int(token))
        if token.isidentifier() and (self.names is None or token in self.names):
            return token
        raise CandidateError(f"Unsupported scalar operand {token!r}")

    def expression(self, minimum=1):
        left = self.atom()
        while self.tokens[self.index] == "as":
            self.take("as")
            self.take(self.cast)
            left = render(("int", left), self.language)
        while PREC.get(self.tokens[self.index], 0) >= minimum:
            op = self.take()
            right = self.expression(PREC[op] + 1)
            left = render(({"&&": "and", "||": "or"}.get(op, op), left, right), self.language)
        return left

    def parse(self):
        try:
            value = self.expression()
        except RecursionError as exc:
            raise CandidateError("Scalar expression nesting limit exceeded") from exc
        if self.tokens[self.index]:
            raise CandidateError(f"Unexpected token {self.tokens[self.index]!r} after the expression")
        return value


def translate(expression, language):
    """Translate a compiler-selected GPT++ scalar expression to native source."""
    if language == "gpp":
        return expression
    if language not in TYPES:
        raise ValueError(f"Unknown language {language!r}")
    return ScalarParser(expression, language).parse()


PYTHON_HELPERS = """def quotient(a: int, b: int) -> int:
    if a == -(2**63) and b == -1:
        raise OverflowError
    return (1 if (a < 0) == (b < 0) else -1) * (abs(a) // abs(b))

def remainder(a: int, b: int) -> int:
    return a - b * quotient(a, b)

def clamp(a: int, lo: int, hi: int) -> int:
    if hi < lo:
        raise ArithmeticError
    return min(max(a, lo), hi)
"""
RUST_HELPERS = """use std::cmp::{min, max};
fn clamp(x: i64, lo: i64, hi: i64) -> i64 { x.clamp(lo, hi) }
fn abs(x: i64) -> i64 { x.abs() }
"""
PYTHON_OBSERVER = """
import json, sys
for line in sys.stdin:
    try:
        value = update(*json.loads(line))
        if type(value) is int and not -(2**63) <= value < 2**63:
            raise OverflowError
    except ArithmeticError:
        value = None
    print(json.dumps(value))
"""


def python_fragment(expression, names):
    try:
        tree = ast.parse(bounded(expression), mode="eval")
    except (SyntaxError, RecursionError) as exc:
        raise CandidateError("Invalid Python expression") from exc
    helpers = {"int", "quotient", "remainder", *ARITY}
    allowed = (ast.Expression, ast.Name, ast.Load, ast.Constant, ast.IfExp, ast.BinOp, ast.UnaryOp,
               ast.Compare, ast.BoolOp, ast.Call, ast.Add, ast.Mult, ast.Sub, ast.Mod, ast.FloorDiv,
               ast.UAdd, ast.USub, ast.Not, ast.And, ast.Or, ast.Eq, ast.NotEq, ast.GtE, ast.Gt,
               ast.Lt, ast.LtE)
    for node in ast.walk(tree):
        if not isinstance(node, allowed):
            raise CandidateError(f"Unsupported Python expression node {type(node).__name__}")
        if isinstance(node, ast.Name) and node.id not in names | helpers:
            raise CandidateError("Unknown binding " + node.id)
        if isinstance(node, ast.Call) and not (isinstance(node.func, ast.Name) and node.func.id in helpers):
            raise CandidateError("Only supplied scalar helpers may be called")
        if isinstance(node, ast.Constant) and (type(node.value) not in (int, bool) or abs(node.value) > 2**63):
            raise CandidateError("Expected a scalar constant")
    return ast.unparse(tree)


def command(argv, stdin=None):
    return subprocess.run(argv, input=stdin, capture_output=True, text=True, timeout=30)


def observe(language, task, expression, inputs, work):
    """Type-check one native replacement and execute each input, returning None on an arithmetic fault.

    Work directories are owned by the caller and should be private to each concurrent trial.
    CandidateError indicates an invalid proposal. Setup errors and timeouts propagate.
    """
    types = TYPES[language]
    names = {name for name, _ in task.args}
    inputs = list(inputs)
    for row in inputs:
        if len(row) != len(task.args) or any(type(value) is not (int if ty == "I64" else bool)
                                           or not -(2**63) <= value < 2**63
                                           for value, (_, ty) in zip(row, task.args)):
            raise ValueError("Observer input is outside its declared signature")
    work = Path(work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    args = ", ".join(f"{name}: {types[ty]}" for name, ty in task.args)
    result_type = types[task.result]
    if language == "python":
        code = python_fragment(expression, names)
        source = work / "candidate.py"
        source.write_text(PYTHON_HELPERS + f"\ndef update({args}) -> {result_type}:\n    return {code}\n")
        # Multiple same-length fragments can replace this path in one filesystem
        # clock tick. Check its contents even when mypy sees an unchanged stat.
        check = command([PYTHON, "-m", "mypy", "--strict", "--no-incremental", "--no-error-summary",
                         "--cache-dir", work / "mypy", source])
        if check.returncode and ("No module named mypy" in check.stderr or check.returncode != 1):
            raise RuntimeError("mypy unavailable or failed: " + (check.stderr or check.stdout))
        if check.returncode:
            raise CandidateError(check.stdout.strip().replace(str(work) + "/", ""))
        with source.open("a") as output:
            output.write(PYTHON_OBSERVER)
        wire = "\n".join(json.dumps(row) for row in inputs)
        run = [PYTHON, "-I", source]
    else:
        ScalarParser(expression, language, names, cast="i64").parse()
        source = work / "candidate.rs"
        rust_args = ", ".join(f"words.next().unwrap().parse::<{types[ty]}>().unwrap()" for _, ty in task.args)
        source.write_text(RUST_HELPERS + f"""
fn update({args}) -> {result_type} {{ {expression} }}
fn main() {{
    use std::io::BufRead;
    std::panic::set_hook(Box::new(|_| {{}}));
    for line in std::io::stdin().lock().lines() {{
        let line = line.unwrap();
        let mut words = line.split_whitespace();
        let value = std::panic::catch_unwind(move || update({rust_args}));
        match value {{ Ok(x) => println!("{{x}}"), Err(_) => println!("null") }}
    }}
}}
""")
        run = [work / "candidate"]
        check = command(["rustc", "--edition=2024", "-A", "warnings", "-C", "overflow-checks=yes",
                         source, "-o", run[0]])
        if check.returncode:
            if "error: linking" in check.stderr or "internal compiler error" in check.stderr:
                raise RuntimeError(check.stderr)
            raise CandidateError(check.stderr.strip().replace(str(work) + "/", "")[:1200])
        wire = "\n".join(" ".join(str(v).lower() for v in row) for row in inputs)
    observed = command(run, wire + ("\n" if inputs else ""))
    if observed.returncode:
        raise RuntimeError(observed.stderr or f"{language} observer failed")
    values = [json.loads(line) for line in observed.stdout.splitlines()]
    if len(values) != len(inputs):
        raise RuntimeError(f"{language} observer lost observations")
    for value in values:
        if value is not None and type(value) is not (int if task.result == "I64" else bool):
            raise CandidateError("Observed value has the wrong scalar type")
    return values
