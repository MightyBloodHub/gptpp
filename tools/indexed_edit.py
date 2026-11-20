#!/usr/bin/env python3
"""Propose one checked expression edit using a numbered compiler catalog and JSON decoding."""

import argparse
import difflib
import json
from pathlib import Path
import shlex
import sys
from tempfile import TemporaryDirectory

import propose


def edit_request(model, language, task, examples, target, spans):
    """Build a request using only the target function, its syntax and public examples."""
    data = target.encode()
    choices = []
    for index, (start, end) in enumerate(spans, 1):
        line = data.count(b"\n", 0, start) + 1
        choices.append(f"{index} (L{line}) {data[start:end].decode()}")
    if not choices:
        raise ValueError("The target has no selectable expressions.")
    names = {"gpp": "GPT++", "python": "typed Python", "rust": "Rust"}
    prompt = "\n".join(
        [
            f"Edit one existing expression in this {names[language]} function.",
            task,
            "Examples",
            *examples[:3],
            "Current function",
            target,
            "Selectable expressions, in source order",
            *choices,
            'Return a JSON object. Set "site" to its listed ID and "replacement" to one native '
            "expression that fixes the task. The editor preserves the rest of the function.",
        ]
    )
    schema = {
        "type": "object",
        "properties": {
            "site": {"type": "string", "enum": [str(i) for i in range(1, len(spans) + 1)]},
            "replacement": {"type": "string"},
        },
        "required": ["site", "replacement"],
        "additionalProperties": False,
    }
    return dict(
        model=model,
        prompt=prompt,
        format=schema,
        stream=False,
        keep_alive="3m",
        options=dict(seed=42, temperature=0, num_ctx=2048, num_predict=240),
    )


def order_spans(ranges):
    return sorted(set(ranges), key=lambda span: (span[0], -span[1]))


def read_change(raw, spans):
    def unique_fields(pairs):
        value = {}
        for name, item in pairs:
            if name in value:
                raise ValueError(f"Duplicate edit field: {name}")
            value[name] = item
        return value

    value = json.loads(raw, object_pairs_hook=unique_fields)
    if not isinstance(value, dict) or value.keys() != {"site", "replacement"}:
        raise ValueError("Expected a site and replacement expression.")
    site = value["site"]
    if not isinstance(site, str) or site not in {str(i) for i in range(1, len(spans) + 1)}:
        raise ValueError("Selected site is outside the checked catalog.")
    fragment = value["replacement"]
    if not isinstance(fragment, str) or not fragment.strip():
        raise ValueError("An edit needs a nonempty replacement.")
    return spans[int(site) - 1], fragment


def propose_edit(args):
    if args.output.exists() or not args.output.parent.is_dir():
        raise ValueError("Supply a new fragment path in an existing directory.")
    if not args.task.strip():
        raise ValueError("Supply a nonempty task description.")
    source = args.file.read_bytes()
    with TemporaryDirectory(prefix="gpp-indexed-") as scratch:
        work = Path(scratch)
        snapshot = work / "base.gpp"
        snapshot.write_bytes(source)
        base = propose.checked(args.gpp, "revision", snapshot).strip()
        catalog = propose.expression_catalog(args.gpp, snapshot, args.function, base)
        start, end = catalog["start_byte"], catalog["end_byte"]
        spans = order_spans((n["start_byte"] - start, n["end_byte"] - start) for n in catalog["expressions"])
        dump = propose.checked(args.gpp, "ast", snapshot)
        declarations = {fn["name"]: fn for fn in propose.FUNCTION.finditer(dump)}
        cases = propose.load_cases(args.cases, args.function, declarations)
        examples = [f"{c.call()} = {c.expected}" for c in cases]
        model, *_ = propose.local_model(args.model, args.port)
        request = edit_request(model, "gpp", args.task, examples, source[start:end].decode(), spans)
        reply = propose.ollama(args.port, "generate", request)
        if reply.get("done") is not True or not isinstance(reply.get("response"), str):
            raise ValueError("Ollama returned an incomplete generation.")
        (a, b), fragment = read_change(reply["response"], spans)
        patch = [
            args.gpp,
            "edit",
            str(args.file),
            "--function",
            args.function,
            "--at",
            f"{start + a}:{start + b}",
            "--expr",
        ]
        content, preview = propose.checked_proposal(
            args.gpp,
            patch,
            base,
            "expr",
            args.function,
            fragment.strip() + "\n",
            work,
            selected_expression=True,
        )
        propose.check_cases(args.gpp, preview, work, cases)
        if propose.checked(args.gpp, "revision", args.file).strip() != base:
            raise ValueError("Source changed while validating the proposal.")
        propose.publish(args.output, content)
    print(
        "\n".join(
            difflib.unified_diff(
                source.decode().splitlines(),
                preview.decode().splitlines(),
                fromfile=str(args.file),
                tofile="checked proposal",
                lineterm="",
            )
        )
    )
    print(f"Passed {len(cases)} supplied examples. Apply the saved expression with")
    print(shlex.join([*patch, str(args.output), "--expect", base]))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("file", type=Path)
    cli.add_argument("--function", required=True)
    cli.add_argument("--task", required=True)
    cli.add_argument("--cases", type=Path, required=True)
    cli.add_argument("--model", default=propose.MAINTENANCE_MODEL)
    cli.add_argument("--port", type=int, default=11434)
    cli.add_argument("--gpp", default=str(propose.ROOT / "target/debug/gpp"))
    cli.add_argument("-o", "--output", type=Path, required=True)
    try:
        propose_edit(cli.parse_args())
    except (propose.ProposalError, ValueError, OSError) as exc:
        sys.exit(str(exc))
