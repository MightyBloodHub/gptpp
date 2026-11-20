"""Replay v1 terminal GPT++ replies. No inference, repairs, or oracle-guided selection."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "bench/empirical"))
from evaluate import Tools, arguments, signature
from maintenance import TASKS as MAINTENANCE
from run import candidate
from synthesis import TASKS as SYNTHESIS


DECLARATION = re.compile(r"(?m)^[ \t]*(?:pub[ \t]+)?fn[ \t]+([A-Za-z_]\w*)\s*\(")
# The body can follow an ordinary return annotation, a missing annotation, or a
# dangling bang. A spelled empty effect set is skipped only if another block follows.
AFTER_PARAMS = re.compile(r"\s*(?:(?:->|→)\s*[A-Za-z_][A-Za-z_0-9]*\s*)?(?:!\s*(?:\{\s*\}\s*(?=\{))?)?")
PREFIX = "module empirical.trial;\n"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def balanced_end(text, start):
    """Scan one complete group, ignoring // line comments. Return exclusive end."""
    opening = text[start]
    closing = {"(": ")", "{": "}"}[opening]
    depth = 0
    i = start
    while i < len(text):
        if text.startswith("//", i):
            while i < len(text) and text[i] not in "\r\n":
                i += 1
            continue
        if text[i] in "'\"`":
            raise ValueError("quoted text or fence inside incomplete group")
        if text[i] == opening:
            depth += 1
        elif text[i] == closing:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    raise ValueError("incomplete group")


def body_range(response):
    declarations = list(DECLARATION.finditer(response))
    if len(declarations) != 1 or declarations[0][1] != "solve":
        raise ValueError("expected exactly one line-start function declaration named solve")
    header_end = balanced_end(response, declarations[0].end() - 1)
    start = AFTER_PARAMS.match(response, header_end).end()
    if response[start:start + 1] != "{":
        raise ValueError("no identifiable body after parameter list")
    return start, balanced_end(response, start)


def entry(args):
    return f"\npub fn main() -> I64 !{{}} {{ return solve({arguments(args, 'gpp')}); }}\n"


def detail(text, work):
    return text.strip().replace(str(work) + "/", "")[:600]


def recover(tools, work, task, response):
    try:
        start, end = body_range(response)
    except ValueError as exc:
        return None, {"stage": "extract_error", "detail": str(exc)}
    frag = work / "body.fragment"
    frag.write_text(response[start:end])
    suffix = entry(task["public"][0][0])
    wrapper = work / "skeleton.gpp"
    header = signature(task, "gpp")
    wrapper.write_text(f"{PREFIX}{header} {{ return 0; }}{suffix}")
    rc, out, err = tools.run(
        [tools.gpp, "edit", wrapper, "--function", "solve", "--body", frag, "--stdout"], work
    )
    facts = {"body_char_range": [start, end], "body_sha256": digest(response[start:end].encode())}
    if rc:
        return None, dict(facts, stage="edit_rejected", detail=detail(err, work))
    if not out.startswith(PREFIX + header + " {") or not out.endswith("}" + suffix):
        raise RuntimeError("edit output did not preserve the declared signature and wrapper")
    return out[len(PREFIX):-len(suffix)], dict(facts, stage="edited")


def score(tools, work, task, code):
    trial = work / "trial.gpp"
    trial.write_text(PREFIX + code + entry(task["public"][0][0]))
    rc, _, err = tools.run([tools.gpp, "check", trial], work)
    if rc:
        return {"checked": False, "detail": detail(err, work)}
    score = {"checked": True}
    for group in ("public", "heldout"):
        cases = task[group]
        counts = {"cases": len(cases), "numeric": 0, "correct": 0}
        failures = Counter()
        for args, expected in cases:
            # Identical wrapper, interpreter, process sandbox and expected-value
            # comparison to v1. Run every case even when an earlier case fails.
            trial.write_text(PREFIX + code + entry(args))
            rc, out, err = tools.run([tools.gpp, "run", "--interpreter", trial], work)
            lines = out.splitlines()
            if rc:
                failures["check" if "error[GPP-" in err else "runtime"] += 1
            elif len(lines) != 1 or not re.fullmatch(r"-?[0-9]+", lines[0]):
                failures["nonnumeric_output"] += 1
            else:
                counts["numeric"] += 1
                if lines[0] == str(expected):
                    counts["correct"] += 1
                else:
                    failures["wrong_answer"] += 1
        score[group] = dict(counts, all_pass=counts["correct"] == len(cases), failures=dict(failures))
    return score


def totals(rows):
    valid = [r for r in rows if r["checked"]]
    return {
        "assigned": len(rows),
        "checked": len(valid),
        "public_all": sum(r["public"]["all_pass"] for r in valid),
        "heldout_all": sum(r["heldout"]["all_pass"] for r in valid),
        "accepted_both": sum(r["public"]["all_pass"] and r["heldout"]["all_pass"] for r in valid),
        **{group: {
            key: sum(r[group][key] for r in valid) for key in ("cases", "numeric", "correct")
        } for group in ("public", "heldout")},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "bench/empirical/results/2026-11-19.jsonl")
    parser.add_argument("--gpp", type=Path, default=ROOT / "target/debug/gpp")
    parser.add_argument("--output", type=Path, default=ROOT / "bench/iterate/results/v1-replay.json")
    args = parser.parse_args()
    records = list(map(json.loads, args.input.read_bytes().splitlines()))
    manifest = records[0]
    for name in ("evaluate.py", "synthesis.py", "maintenance.py", "run.py"):
        path = Path("bench/empirical") / name
        if digest((ROOT / path).read_bytes()) != manifest["file_sha256"][str(path)]:
            raise RuntimeError(f"v1 evaluator or corpus changed: {path}")
    tools = Tools(ROOT, args.gpp)
    tools.canaries()
    compiler_digest = digest(tools.gpp.read_bytes())
    tasks = {t["id"]: t for t in [*SYNTHESIS, *MAINTENANCE]}
    rows = []
    for record in records[1:]:
        if record["language"] != "gpp":
            continue
        task = tasks[record["task"]]
        response = record["attempts"][-1]["response"]
        with tempfile.TemporaryDirectory(prefix="gpp-v1-replay-") as temp:
            work = Path(temp).resolve()
            original = candidate(response)
            direct = score(tools, work, task, original)
            body, extraction = recover(tools, work, task, response)
            edited = {"checked": False} if body is None else score(tools, work, task, body)
        row = {
            "model": record["model"], "task": task["id"],
            "original_v1_outcome": record["attempts"][-1]["outcome"],
            "raw_response_sha256": digest(response.encode()),
            "direct_source_sha256": digest(original.encode()),
            "body_source_sha256": digest(body.encode()) if body is not None else None,
            "direct": direct, "extraction": extraction, "body": edited,
            "fallback_selected": "direct" if direct["checked"] else "body",
        }
        rows.append(row)
    cells = {(r["model"], r["task"]) for r in rows}
    if len(rows) != 24 or cells != {(m, t) for m in manifest["models"] for t in manifest["tasks"]}:
        raise RuntimeError("incomplete or duplicate terminal GPT++ cells")
    if compiler_digest != digest(tools.gpp.read_bytes()):
        raise RuntimeError("compiler changed during replay")
    report = {
        "study": "v1 terminal GPT++ offline replay",
        "input_sha256": digest(args.input.read_bytes()),
        "original_compiler_sha256": manifest["gpp_sha256"],
        "current_compiler_sha256": compiler_digest,
        "replay_script_sha256": digest(Path(__file__).read_bytes()),
        "rules": [
            "Use the final recorded reply, original fence extraction for direct, current checker/interpreter and unchanged v1 oracles.",
            "Body recovery requires one line-start fn solve declaration, balanced parentheses, a recognizable header, and a complete brace group; skip // line comments. Retain the exact brace-delimited source slice.",
            "Apply the body with gpp edit --body --stdout to the task's fixed signature, then evaluate the emitted function. Never rewrite statements or use expected outputs in extraction.",
            "Score all public and all held-out cases for every checked candidate, independently. Numeric counts exact single integer outputs. Acceptance requires both suites.",
            "Fallback uses direct output whenever it checks and uses the body arm only on a compile failure. This decision has no access to test outcomes.",
        ],
        "original_accepted": sum(r["original_v1_outcome"] == "accepted" for r in rows),
        "original_public_all": sum(r["attempts"][-1]["public_outcome"] == "pass"
                                   for r in records[1:] if r["language"] == "gpp"),
        "totals": {
            "direct": totals([r["direct"] for r in rows]),
            "body": totals([r["body"] for r in rows]),
            "fallback": totals([r[r["fallback_selected"]] for r in rows]),
        },
        "extraction_stages": dict(Counter(r["extraction"]["stage"] for r in rows)),
        "results": rows,
    }
    args.output.parent.mkdir(exist_ok=True, parents=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("totals", "extraction_stages")}, indent=2))


if __name__ == "__main__":
    main()
