"""Lower ordered scalar decision rules to a checked GPT++ function body.

Each non-comment line is either 'when CONDITION => VALUE' or 'else => VALUE'.
The final else is required. Expressions use the checked scalar Python surface.
"""

import argparse
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from textwrap import dedent

from scalar_builtins import lower_fragment
from scalar_fragment import parameter


MAX_SOURCE_BYTES = 65536


def _typed_expression(source, kind, params):
    """Use the scalar translator's type rules for both guards and results."""
    if not source:
        raise ValueError("expected an expression")
    # Validate the unwrapped expression first, so mismatched parentheses cannot
    # consume delimiters from the type probe. Emit the original version only.
    emitted = lower_fragment(source, "expr", params)
    operator = "+" if kind == "int" else "not "
    lower_fragment(f"{operator}({source})", "expr", params)
    return emitted


def lower_policy(text, params, result="int", *, original_body=None):
    """Return a bare GPT++ body. Params are (name, 'int'|'bool') pairs.

    The special final value @keep falls through to original_body, which the
    caller must obtain from the checked target. Raises ValueError on bad input.
    """
    if not isinstance(text, str):
        raise ValueError("expected policy text")
    if len(text) > MAX_SOURCE_BYTES or len(text.encode("utf-8")) > MAX_SOURCE_BYTES:
        raise ValueError(f"policy exceeds {MAX_SOURCE_BYTES} UTF-8 bytes")
    if result not in ("int", "bool"):
        raise ValueError("policy result type must be int or bool")
    try:
        params = list(params)
    except TypeError as exc:
        raise ValueError("expected a sequence of (name, type) parameters") from exc
    if any(not isinstance(p, (tuple, list)) or len(p) != 2 for p in params):
        raise ValueError("expected (name, type) parameter pairs")
    # A policy consisting only of the @keep fallback has no scalar expression
    # on which to check the parameter declaration.
    lower_fragment("0", "expr", params)
    body = []
    default_seen = False
    for number, line in enumerate(text.splitlines(), 1):
        row = line.strip(" \t")
        if not row or row.startswith("#"):
            continue
        try:
            if default_seen:
                raise ValueError("else must be the final rule")
            if not row.isascii() or "#" in row:
                raise ValueError("use ASCII rule text and put comments on separate lines")
            if row.count("=>") != 1:
                raise ValueError("expected one => between the rule and its value")
            head, value = (part.strip() for part in row.split("=>"))
            if head == "else":
                if value == "@keep":
                    if not isinstance(original_body, str) or not original_body.strip():
                        raise ValueError("@keep requires the checked target's original body")
                    body.append(dedent(original_body).strip("\n"))
                else:
                    body.append(f"return {_typed_expression(value, result, params)};")
                default_seen = True
                continue
            parts = head.split(maxsplit=1)
            if len(parts) != 2 or parts[0] != "when":
                raise ValueError("expected 'when <condition>' or 'else'")
            if value == "@keep":
                raise ValueError("@keep is only allowed in the final else rule")
            guard = _typed_expression(parts[1], "bool", params)
            answer = _typed_expression(value, result, params)
            body.extend((f"if {guard} {{", f"    return {answer};", "}"))
        except ValueError as exc:
            raise ValueError(f"policy line {number}: {exc}") from exc
    if not default_seen:
        raise ValueError("policy requires a final 'else => <value>' rule")
    return "\n".join(body)


def checked_edit(text, args):
    # Import at CLI runtime so the standalone lowering API needs no tooling
    # for model proposals. These helpers only invoke the local GPT++ compiler.
    from propose import ProposalError, checked, parameters, target_context
    scalar_types = {"I64": "int", "Bool": "bool"}
    with TemporaryDirectory(prefix="gpp-policy-") as scratch:
        base = Path(scratch) / "base.gpp"
        base.write_bytes(args.source.read_bytes())
        try:
            checked(args.gpp, "check", base)
            revision = checked(args.gpp, "revision", base).strip()
            target, _ = target_context(checked(args.gpp, "ast", base), args.function)
            inputs = parameters(target)
            if target["result"] not in scalar_types or any(t not in scalar_types for _, t in inputs):
                raise ValueError("policy parameters and result must be I64 or Bool")
            body = lower_policy(text, [(name, scalar_types[t]) for name, t in inputs],
                                scalar_types[target["result"]], original_body=target["body"])
            fragment = Path(scratch) / "body.gpp"
            fragment.write_text(body, encoding="utf-8")
            command = ["edit", args.source, "--function", args.function, "--body", fragment, "--expect", revision]
            if not args.apply:
                command.append("--stdout")
            output = checked(args.gpp, *command)
            return output if args.preview or args.apply else body + "\n"
        except ProposalError as exc:
            raise ValueError(str(exc)) from exc


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--param", action="append", default=[], type=parameter, metavar="NAME:TYPE")
    cli.add_argument("--result", choices=("int", "bool"), help="result type for standalone lowering (default: int)")
    cli.add_argument("--source", type=Path, help="derive the signature and original body from this checked module")
    cli.add_argument("--function", help="name of the function in --source")
    cli.add_argument("--gpp", default=str(Path(__file__).resolve().parents[1] / "target/debug/gpp"))
    mode = cli.add_mutually_exclusive_group()
    mode.add_argument("--preview", action="store_true", help="print the full checked edited module")
    mode.add_argument("--apply", action="store_true", help="apply the checked edit to --source with a revision guard")
    args = cli.parse_args()
    if bool(args.source) != bool(args.function):
        cli.error("--source and --function must be supplied together")
    if args.source and (args.param or args.result):
        cli.error("--source derives the parameters and result from the target")
    if not args.source and (args.preview or args.apply):
        cli.error("--preview and --apply require --source and --function")
    try:
        source = sys.stdin.buffer.read(MAX_SOURCE_BYTES + 1)
        if len(source) > MAX_SOURCE_BYTES:
            raise ValueError(f"policy exceeds {MAX_SOURCE_BYTES} UTF-8 bytes")
        text = source.decode("utf-8")
        if args.source:
            sys.stdout.write(checked_edit(text, args))
        else:
            print(lower_policy(text, args.param, args.result or "int"))
    except (ValueError, OSError, subprocess.TimeoutExpired) as exc:
        cli.exit(1, f"{exc}\n")
