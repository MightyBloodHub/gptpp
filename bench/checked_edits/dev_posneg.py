"""Repair the archived posNeg compiler candidate once using only public development data."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from time import monotonic

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import acceptance
from propose import ollama

MODEL = "qwen2.5-coder:7b"
DIGEST = "dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364"
ARCHIVED_QWEN = "(negative && (a < 0) && (b < 0)) || (!negative && ((a > 0) && (b < 0)))"
ARCHIVED_COMPILER = "if negative { (a <= 0) } else { ((b * a) <= -1) }"
ARCHIVED_REVISION = "sha256:645e4395b603c2470e4d06df6eb231d243fcda3078e989f864e9611211a334b1"
# Copied from the historical model's public prompt. Pin the resulting compiler
# input revision so this demo never needs to import the archive or scorer.
EXAMPLES = [
    (1, -1, False, True), (-1, 1, False, True), (-4, -5, True, True),
    (-6, -6, False, False), (6, 6, True, False), (6, 6, False, False),
    (-2, -5, False, False), (0, 5, False, False), (-1, -5, False, False),
    (1, 4, True, False), (-3, -1, True, True), (-3, -5, True, True),
    (6, -3, False, True), (6, -5, False, True), (-1, -1, True, True),
    (1, -6, True, False), (6, 1, False, False), (2, -1, True, False),
    (3, -6, True, False), (4, 0, False, False), (6, 3, False, False),
    (3, 5, True, False), (-5, -3, False, False), (4, 1, True, False),
]
SOURCE = """module study.search;
fn transition(a: I64, b: I64, negative: Bool) -> Bool !{} {
    return ?change: Bool;
}
pub fn main() -> I64 !{} { return 0; }
"""
SPEC = "Normally require one strictly positive integer and one strictly negative integer. In negative mode require both integers to be negative. Zero has neither sign."
CONTRACT = {"name": "public_sign_rule", "mode": "finite", "rule": SPEC,
            "declaration": """contract public_sign_rule(a: I64 in -8..=8, b: I64 in -8..=8, negative: Bool) {
    transition(a, b, negative) == (if negative { max(a, b) < 0 }
        else { a != 0 && b != 0 && ((a < 0) != (b < 0)) })
}"""}
REFERENCE = "if negative { a < 0 && b < 0 } else { (a < 0 && b > 0) || (b < 0 && a > 0) }"


def sketch_text():
    rows = []
    for i, (a, b, mode, expected) in enumerate(EXAMPLES):
        args = f"{a}, {b}, {json.dumps(mode)}"
        rows.append(f"contract sample_{i}() {{ transition({args}) == {json.dumps(expected)} }}\n")
    return SOURCE + "".join(rows)


def make_request(failure):
    site = failure["edit_site"]
    observation, = failure["observed"]
    prompt = "\n".join([
        "Repair the single Bool expression in transition(a: I64, b: I64, negative: Bool) -> Bool in GPT++.",
        f"Public rule: {failure['rule']}",
        f"Editable expression ({site['name']}: {site['type']}): {site['previous']}",
        f"The compiler replayed this failing input: {json.dumps(failure['inputs'])}",
        f"Observed result: {json.dumps(observation['value'])}. The Boolean result violates the public rule.",
        "GPT++ supports if condition { yes } else { no }, comparisons, &&, || and !.",
        'Return a JSON object with the replacement expression in its "expression" field.',
    ])
    return {"model": MODEL, "prompt": prompt, "stream": False, "keep_alive": "3m",
            "format": {"type": "object", "properties": {"expression": {"type": "string"}},
                       "required": ["expression"], "additionalProperties": False},
            "options": {"temperature": 0, "num_predict": 200, "num_ctx": 4096, "seed": 43}}


def demo(binary, work, *, live):
    start = monotonic()
    sketch = work / "sketch.gpp"
    sketch.write_text(sketch_text())
    assert acceptance.revision(sketch.read_bytes()) == ARCHIVED_REVISION
    captures = []
    saved = None if live else json.loads(Path(__file__).with_name("dev_posneg_capture.json").read_text())
    if saved and saved["model_digest"] != DIGEST:
        raise ValueError("Archived development model digest changed")

    def check(expr, source):
        return acceptance.check_candidate(binary, sketch, expr, source, [CONTRACT])

    def ask(failure):
        if not failure or captures:
            raise RuntimeError("Development repair requires one public failure and at most one model call")
        request = make_request(failure)
        if saved:
            receipt, = saved["model_calls"]
            if request != receipt["request"]:
                raise ValueError("Public counterexample or repair request changed")
            captures.append(receipt)
            return json.loads(receipt["response"])["expression"]
        began = monotonic()
        answer = ollama(11434, "generate", request)
        seconds = monotonic() - began
        if not answer.get("done") or not all(type(answer.get(k)) is int for k in ("prompt_eval_count", "eval_count")):
            raise ValueError("Incomplete inference receipt")
        try:
            parsed = json.loads(answer["response"])
            expr = parsed["expression"] if set(parsed) == {"expression"} and type(parsed["expression"]) is str else ""
        except (ValueError, KeyError, TypeError):
            expr = ""
        captures.append({"request": request, "response": answer["response"], "stop_reason": answer["done_reason"],
                         "input_tokens": answer["prompt_eval_count"], "output_tokens": answer["eval_count"],
                         "wall_seconds": seconds})
        return expr

    reference = check(REFERENCE, "independent reference expression")
    assert reference["decision"] == "accept", reference
    archived_model = check(ARCHIVED_QWEN, "archived Qwen GPT++ reply")
    assert archived_model["reason"] == "public_example", archived_model
    found = acceptance.search(binary, sketch)
    assert found["selected"] == ARCHIVED_COMPILER, found
    if live and {m["name"]: m["digest"] for m in ollama(11434, "tags")["models"]}.get(MODEL) != DIGEST:
        raise ValueError("Historical Qwen model digest unavailable")
    outcome = acceptance.run_policy(found, check, ask)
    assert outcome["model_calls"] == len(captures) == 1, outcome
    if saved and (outcome["decision"], outcome["selected"]) != (
            saved["workflow"]["decision"], saved["workflow"]["selected"]):
        raise ValueError("Public gate changed the archived repair disposition")
    kind = "newly executed development repair" if live else "archived development repair replay"
    return {"trial_kind": kind, "task": "posNeg", "new_model_calls": int(live),
            "captured_at": datetime.now(timezone.utc).isoformat(), "model_digest": DIGEST,
            "public_rule_source": "bench/search-confirmation/corpus.py, posNeg request from CodingBat p159227",
            "specification_charge": {"new_finite_contracts": 1, "supplied_examples": len(EXAMPLES),
                                     "external_labels": 0, "historical_model_calls_reused": 1},
            "replayed_qwen": archived_model, "reference_validation": reference, "workflow": outcome,
            "model_calls": captures, "wall_seconds_including_preflight": monotonic() - start}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpp", type=Path, default=ROOT / "target/release/gpp")
    parser.add_argument("--live", action="store_true", help="issue a new local Qwen request")
    args = parser.parse_args()
    with TemporaryDirectory(prefix="gpp-posneg-") as directory:
        print(json.dumps(demo(args.gpp.resolve(), Path(directory), live=args.live), indent=2))


if __name__ == "__main__":
    main()
