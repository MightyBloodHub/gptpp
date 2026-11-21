"""Replay the development example, or explicitly collect a new one-call Qwen repair."""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import acceptance


SPEC = "Accept when either argument is ten or their sum is ten."
OLD = "(((b + a) == 10) || (b == 10))"
CORRECT = "a == 10 || b == 10 || a+b == 10"
MODEL = "qwen2.5-coder:7b"
DIGEST = "dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364"


def run(gpp, live, port):
    sketch = HERE / "public.gpp"
    contracts = json.loads((HERE / "contracts.json").read_text())
    weak = json.loads((HERE / "weak.json").read_text())
    calls = []
    if live:
        propose = acceptance.local_proposer(gpp, sketch, SPEC, "change", MODEL, port, calls)
    else:
        archived = json.loads((HERE / "development.json").read_text())["model_usage"]

        def propose(feedback):
            req = acceptance.model_request(MODEL, SPEC, feedback["edit_site"], feedback)
            saved = archived[len(calls)]
            if req != saved["request"] or saved["digest"] != DIGEST:
                raise ValueError("Development replay changed the archived request or pinned model")
            calls.append(saved)
            return json.loads(saved["reply"]["response"])["expression"]

    positive = acceptance.check_candidate(gpp, sketch, CORRECT, "reference:public rule", contracts)
    negative = acceptance.check_candidate(gpp, sketch, OLD, "regression:archived piecewise", contracts)
    weak_pass = acceptance.check_candidate(gpp, sketch, OLD, "regression:archived piecewise", weak)
    if (positive["decision"], negative["decision"], weak_pass["decision"]) != ("accept", "reject", "accept"):
        raise ValueError("Development calibration changed")
    decision = acceptance.run_workflow(gpp, sketch, contracts, propose)
    if decision["search"].get("selected") != OLD:
        raise ValueError("Development search no longer reproduced the historical candidate")
    if len(calls) != 1 or calls[0]["digest"] != DIGEST:
        raise ValueError("Expected one call to pinned local Qwen")
    return {"dataset": "development (historical makes10)", "model_source": "newly executed" if live else "archived replay",
            "reference": positive, "negative_control": negative, "weak_contract": weak_pass,
            "workflow": decision, "model_usage": calls}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--gpp", default=ROOT / "target/release/gpp", type=Path)
    parser.add_argument("--port", default=11434, type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    record = json.dumps(run(args.gpp, args.live, args.port), indent=2) + "\n"
    if args.output:
        args.output.write_text(record)
    else:
        print(record, end="")
