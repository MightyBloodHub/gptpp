"""Product extension of the checked Python-syntax scalar fragment translator.

abs(x), min(x, y) and max(x, y) use I64 operands. Their comparisons evaluate
operands eagerly, left to right. A successful operand may be evaluated again
when selected. The underlying expression language is pure and deterministic.
"""
import ast
from itertools import islice
from textwrap import dedent

from scalar_fragment import lower_fragment as lower_core
from scalar_fragment import reject


ARITY = {"abs": 1, "min": 2, "max": 2}
MAX_EXPANDED_NODES = 1024


class ExpandBuiltins(ast.NodeTransformer):
    def __init__(self, shadowed):
        self.shadowed = shadowed

    def visit_Call(self, node):
        if not isinstance(node.func, ast.Name) or node.func.id not in ARITY:
            reject(node, "only the scalar builtins abs, min and max can be called")
        name = node.func.id
        if name in self.shadowed:
            reject(node, f"builtin {name} is shadowed by a parameter or local binding")
        if node.keywords or any(isinstance(arg, ast.Starred) for arg in node.args):
            reject(node, f"{name} requires plain positional arguments")
        if len(node.args) != ARITY[name]:
            reject(node, f"{name} requires {ARITY[name]} positional arguments")
        args = [self.visit(arg) for arg in node.args]
        first = args[0]
        if name == "abs":
            test = ast.Compare(first, [ast.Lt()], [ast.Constant(0)])
            yes = ast.UnaryOp(ast.USub(), first)
            no = first
        else:
            # Integer ordering checks both types in the original translator.
            # Evaluating the comparison first also retains the first observable fault.
            op = ast.LtE() if name == "min" else ast.GtE()
            test = ast.Compare(first, [op], [args[1]])
            yes, no = args
        return ast.copy_location(ast.IfExp(test, yes, no), node)


def lower_fragment(text, form, parameters):
    """Lower a scalar fragment with checked builtins, or raise ValueError."""
    if form not in ("expr", "body"):
        raise ValueError("form must be expr or body")
    try:
        tree = ast.parse(dedent(text).strip() if form == "expr" else dedent(text),
                         mode="eval" if form == "expr" else "exec")
        if not any(isinstance(node, ast.Call) for node in ast.walk(tree)):
            return lower_core(text, form, parameters)
        parameters = list(parameters)
        bound = {name for name, _ in parameters}
        bound.update(n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store))
        expanded = ExpandBuiltins(bound).visit(tree)
        # Reused nodes form a DAG until unparsing. Count occurrences, including
        # duplicates, and stop before materializing an exponentially larger source.
        if next(islice(ast.walk(expanded), MAX_EXPANDED_NODES, None), None) is not None:
            raise ValueError(f"builtin expansion exceeds {MAX_EXPANDED_NODES} AST nodes; bind intermediates to locals")
        return lower_core(ast.unparse(expanded), form, parameters)
    except SyntaxError as exc:
        raise ValueError(f"line {exc.lineno}, column {exc.offset}: {exc.msg}") from exc
    except RecursionError as exc:
        raise ValueError("fragment exceeds Python parser or translator nesting limits") from exc
