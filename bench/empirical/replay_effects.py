"""Replay terminal GPT++ candidates after inserting one diagnosed empty effect set."""

import argparse
import json
from pathlib import Path
import re

from evaluate import Tools
from run import ROOT, candidate
from maintenance import TASKS as MAINTENANCE
from synthesis import TASKS as SYNTHESIS


MISSING_EFFECT = re.compile(
    r"^trial\.gpp:(\d+):(\d+): error\[GPP-PARSE-001\]: expected '!', found '\{'"
)


def with_effect(source, line, column):
    # The evaluator prepends one module declaration before the candidate.
    lines = source.splitlines(keepends=True)
    index = line - 2
    if not 0 <= index < len(lines) or lines[index][column - 1:column] != "{":
        raise ValueError("Diagnostic does not identify the opening brace in the candidate")
    lines[index] = lines[index][:column - 1] + " !{} " + lines[index][column - 1:]
    return "".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--gpp", type=Path, default=ROOT / "target/debug/gpp")
    args = parser.parse_args()
    tasks = {task["id"]: task for task in [*SYNTHESIS, *MAINTENANCE]}
    tools = Tools(ROOT, args.gpp)
    tools.canaries()
    results = []
    with args.input.open() as data:
        metadata = json.loads(next(data))
        for line in data:
            record = json.loads(line)
            if record["language"] != "gpp" or record["accepted"]:
                continue
            terminal = record["attempts"][-1]
            match = MISSING_EFFECT.match(terminal["public_detail"])
            if not match:
                continue
            code = with_effect(candidate(terminal["response"]), *map(int, match.groups()))
            task = tasks[record["task"]]
            status, _ = tools.evaluate(task, "gpp", code, task["public"] + task["heldout"])
            results.append((record["model"], record["task"], status))

    print(f"## Empty effect annotation replay\n")
    print(
        f"The post-hoc replay selected {len(results)} terminal GPT++ failures from "
        f"`{metadata['study']}` whose first diagnostic identified an omitted effect set. "
        "It inserted one `!{}` at the diagnostic location, then ran the original checks. "
        "It used no additional model calls. These outcomes leave the primary pilot scores unchanged.\n"
    )
    print(f"Accepted after insertion: **{sum(row[2] == 'pass' for row in results)}/{len(results)}**.\n")
    print("| Model | Task | Outcome after insertion |")
    print("|---|---|---|")
    for model, task, status in results:
        print(f"| {model} | {task} | {status} |")


if __name__ == "__main__":
    main()
