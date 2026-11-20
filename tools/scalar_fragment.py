"""Lower a Python-syntax scalar fragment into a GPT++ expression or function body.

The source uses GPT++ I64 and Bool semantics. Integer arithmetic is checked.
The // operator truncates toward zero, and % follows the same quotient. Logical
operators require booleans. Conditions and logical operands are lazy. Locals
introduced in a branch or loop are visible only inside that suite. A value that
must survive a suite needs a real initialization in an enclosing scope.

Supply the function parameters as (name, 'int' or 'bool') pairs. The destination
function and its declared result type are checked by gpp edit. This adapter
inspects syntax trees and emits source. It never executes a submitted fragment.
"""

import argparse
import ast
from collections import Counter
from dataclasses import dataclass
import keyword
import sys
from textwrap import dedent


RESERVED = set("""module pub fn let var return if else while true false use record enum
                  const test requires ensures for in match break continue assert""".split())
ARITHMETIC = {
    ast.Add: ("+", 5), ast.Sub: ("-", 5), ast.Mult: ("*", 6),
    ast.FloorDiv: ("/", 6), ast.Mod: ("%", 6),
}
COMPARISON = {
    ast.Eq: ("==", 3), ast.NotEq: ("!=", 3), ast.Lt: ("<", 4),
    ast.LtE: ("<=", 4), ast.Gt: (">", 4), ast.GtE: (">=", 4),
}


def reject(node, message):
    raise ValueError(f"line {node.lineno}, byte {node.col_offset + 1}: {message}")


@dataclass(frozen=True)
class Value:
    text: str
    kind: str
    precedence: int = 8

    def at(self, minimum):
        return f"({self.text})" if self.precedence < minimum else self.text


def require(value, kind, node):
    if value.kind != kind:
        reject(node, f"expected {kind}, found {value.kind}")
    return value


def infix(left, operator, right, precedence, kind):
    # Preserve the AST's grouping, including right-nested sums and products.
    # Reassociation can change which checked operation faults.
    return Value(f"{left.at(precedence)} {operator} {right.at(precedence + 1)}", kind, precedence)


def arithmetic(op, node):
    if type(op) not in ARITHMETIC:
        reject(node, f"unsupported arithmetic operator {type(op).__name__}; use // for integer division")
    return ARITHMETIC[type(op)]


def expression(node, scope):
    if isinstance(node, ast.Constant):
        if type(node.value) is bool:
            return Value(str(node.value).lower(), "bool")
        if type(node.value) is int and 0 <= node.value < 2**63:
            return Value(str(node.value), "int")
        reject(node, "expected an I64 or Bool literal")
    if isinstance(node, ast.Name):
        if node.id not in scope:
            reject(node, f"'{node.id}' has no initialized binding in this scope")
        return scope[node.id]
    if isinstance(node, ast.UnaryOp):
        if (isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant)
                and type(node.operand.value) is int and node.operand.value == 2**63):
            return Value("-9223372036854775808", "int", 7)
        operand = expression(node.operand, scope)
        if isinstance(node.op, (ast.USub, ast.UAdd)):
            require(operand, "int", node.operand)
            return Value("-" + operand.at(7), "int", 7) if isinstance(node.op, ast.USub) else operand
        if isinstance(node.op, ast.Not):
            return Value("!" + require(operand, "bool", node.operand).at(7), "bool", 7)
        reject(node, f"unsupported unary operator {type(node.op).__name__}")
    if isinstance(node, ast.BinOp):
        op, precedence = arithmetic(node.op, node)
        left = require(expression(node.left, scope), "int", node.left)
        right = require(expression(node.right, scope), "int", node.right)
        return infix(left, op, right, precedence, "int")
    if isinstance(node, ast.BoolOp):
        operator, precedence = ("&&", 2) if isinstance(node.op, ast.And) else ("||", 1)
        parts = [require(expression(value, scope), "bool", value).at(precedence)
                 for value in node.values]
        return Value(f" {operator} ".join(parts), "bool", precedence)
    if isinstance(node, ast.Compare):
        left = expression(node.left, scope)
        result = None
        for index, (op, rhs) in enumerate(zip(node.ops, node.comparators)):
            if type(op) not in COMPARISON:
                reject(node, f"unsupported comparison {type(op).__name__}")
            # Compound middle operands would need an expression-local temporary
            # to guarantee evaluation once. Names and literals have no side effects.
            if index < len(node.ops) - 1 and not isinstance(rhs, (ast.Name, ast.Constant)):
                reject(rhs, "bind this middle comparison operand to a local first")
            right = require(expression(rhs, scope), left.kind, rhs)
            if not isinstance(op, (ast.Eq, ast.NotEq)):
                require(left, "int", node)
            operator, precedence = COMPARISON[type(op)]
            comparison = infix(left, operator, right, precedence, "bool")
            result = comparison if result is None else infix(result, "&&", comparison, 2, "bool")
            left = right
        return result
    if isinstance(node, ast.IfExp):
        cond = require(expression(node.test, scope), "bool", node.test)
        yes = expression(node.body, scope)
        no = require(expression(node.orelse, scope), yes.kind, node.orelse)
        return Value(f"if {cond.text} {{ {yes.text} }} else {{ {no.text} }}", yes.kind)
    reject(node, f"unsupported expression {type(node).__name__}")


class Body:
    def __init__(self, tree, parameters):
        names = [n for n in ast.walk(tree) if isinstance(n, ast.Name)]
        self.writes = Counter(n.id for n in names if isinstance(n.ctx, ast.Store))
        self.used = set(parameters) | {n.id for n in names} | RESERVED
        self.lines = []
        self.scope = dict(parameters)
        for name, param in parameters.items():
            if self.writes[name]:
                alias = self.fresh(name)
                self.lines.append(f"var {alias} = {name};")
                self.scope[name] = Value(alias, param.kind)

    def fresh(self, name):
        root = name + "_local"
        result = root
        suffix = 2
        while result in self.used:
            result = f"{root}_{suffix}"
            suffix += 1
        self.used.add(result)
        return result

    def assignment(self, stmt, scope):
        augmented = isinstance(stmt, ast.AugAssign)
        target = stmt.target if augmented else stmt.targets[0]
        if not isinstance(target, ast.Name) or (not augmented and len(stmt.targets) != 1):
            reject(stmt, "assignment requires one named local")
        name = target.id
        if not name.isascii():
            reject(target, "local names must be ASCII identifiers")
        value = expression(stmt.value, scope)
        if augmented:
            bound = require(expression(target, scope), "int", target)
            require(value, "int", stmt.value)
            op, _ = arithmetic(stmt.op, stmt)
            return f"{bound.text} {op}= {value.text};"
        if name in scope:
            bound = scope[name]
            require(value, bound.kind, stmt.value)
            return f"{bound.text} = {value.text};"
        emitted = self.fresh(name) if name in RESERVED else name
        scope[name] = Value(emitted, value.kind)
        binding = "var" if self.writes[name] > 1 else "let"
        return f"{binding} {emitted} = {value.text};"

    def suite(self, statements, scope, depth):
        indent = "    " * depth
        for stmt in statements:
            if isinstance(stmt, (ast.Assign, ast.AugAssign)):
                self.lines.append(indent + self.assignment(stmt, scope))
            elif isinstance(stmt, ast.Return):
                if stmt.value is None:
                    reject(stmt, "return requires a scalar value")
                self.lines.append(f"{indent}return {expression(stmt.value, scope).text};")
            elif isinstance(stmt, ast.If):
                header = "if"
                while True:
                    condition = require(expression(stmt.test, scope), "bool", stmt.test)
                    self.lines.append(f"{indent}{header} {condition.text} {{")
                    self.suite(stmt.body, scope.copy(), depth + 1)
                    if len(stmt.orelse) == 1 and isinstance(stmt.orelse[0], ast.If):
                        stmt = stmt.orelse[0]
                        header = "} else if"
                        continue
                    if stmt.orelse:
                        self.lines.append(indent + "} else {")
                        self.suite(stmt.orelse, scope.copy(), depth + 1)
                    self.lines.append(indent + "}")
                    break
            elif isinstance(stmt, ast.While):
                if stmt.orelse:
                    reject(stmt, "while-else is unsupported")
                condition = require(expression(stmt.test, scope), "bool", stmt.test)
                self.lines.append(f"{indent}while {condition.text} {{")
                self.suite(stmt.body, scope.copy(), depth + 1)
                self.lines.append(indent + "}")
            else:
                reject(stmt, f"unsupported statement {type(stmt).__name__}")


def lower_fragment(text, form, parameters):
    """Return a GPT++ expression or bare statement list; raise ValueError on invalid input."""
    if form not in ("expr", "body"):
        raise ValueError("form must be expr or body")
    params = {}
    for name, kind in parameters:
        if (not isinstance(name, str) or not name.isascii() or not name.isidentifier()
                or keyword.iskeyword(name) or name in RESERVED or name in params):
            raise ValueError(f"invalid or duplicate parameter {name!r}")
        if kind not in ("int", "bool"):
            raise ValueError(f"unsupported parameter type {kind!r}")
        params[name] = Value(name, kind)
    source = dedent(text).strip("\r\n")
    try:
        if form == "expr":
            tree = ast.parse(source.strip(), mode="eval")
            return expression(tree.body, params).text
        tree = ast.parse(source, mode="exec")
        if not tree.body:
            raise ValueError("expected a nonempty scalar function body")
        body = Body(tree, params)
        body.suite(tree.body, body.scope, 0)
        return "\n".join(body.lines)
    except SyntaxError as err:
        raise ValueError(f"line {err.lineno}, column {err.offset}: {err.msg}") from err
    except RecursionError as err:
        raise ValueError("fragment exceeds Python parser or translator nesting limits") from err


def parameter(argument):
    name, sep, kind = argument.partition(":")
    if not sep or kind not in ("int", "bool"):
        raise argparse.ArgumentTypeError("expected NAME:int or NAME:bool")
    return (name, kind)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("form", choices=("expr", "body"))
    cli.add_argument("--param", action="append", type=parameter, default=[], metavar="NAME:TYPE")
    args = cli.parse_args()
    try:
        print(lower_fragment(sys.stdin.read(), args.form, args.param))
    except ValueError as err:
        cli.exit(1, f"{err}\n")
