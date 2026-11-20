"""Replay archived v3 final completions through the original and extended scalar projections."""

import argparse
from collections import Counter
import hashlib
import json
from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import run_infill as study


ROOT = study.pilot.ROOT
FROZEN = "frozen_v3"
EXTENDED = "posthoc_scalar_builtins"
SOURCES = ("python_fim", "gpp_projected")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fingerprint(source):
    return sha(source.encode("utf-8"))


def validate_log(blob):
    manifest, *rows = map(json.loads, blob.splitlines())
    if manifest.get("study") != "scalar-infill-replication-v3":
        raise ValueError("expected the archived v3 infill study")
    keys = [(r["model"], r["seed"], r["task"], r["condition"]) for r in rows]
    expected = set(product(manifest["models"], manifest["seeds"], manifest["tasks"], study.CONDITIONS))
    if len(rows) != 40 or len(expected) != 40 or set(keys) != expected:
        raise ValueError("replay requires the complete 40-cell v3 matrix with no duplicates")
    if set(manifest["conditions"]) != set(study.CONDITIONS) or len(manifest["tasks"]) != 8:
        raise ValueError("unexpected v3 study design")
    return manifest, {(r["condition"], r["task"]): r for r in rows if r["condition"] in SOURCES}


def verify_sources(manifest, compiler):
    for name, value in manifest["file_sha256"].items():
        if sha((ROOT / name).read_bytes()) != value:
            raise ValueError(f"v3 dependency differs from its archived digest: {name}")
    if sha(compiler.read_bytes()) != manifest["gpp_sha256"]:
        raise ValueError("compiler differs from the archived v3 executable")


def projected(tools, task, raw, adapter):
    # Observe the actual v3 materialization pipeline. Each wrapper forwards its
    # inputs and outputs unchanged; only the explicitly selected lowerer varies.
    original_edit = study.edited_function
    trace = {}

    def edit(tools, task, language, fragment):
        stage = "python_fragment" if language == "python" else "gpp_edit"
        trace["stage"] = stage
        status, detail, code = original_edit(tools, task, language, fragment)
        if status == "pass":
            trace[stage + "_source_sha256"] = fingerprint(code)
        return status, detail, code

    def lower(fragment, form, params):
        trace["stage"] = "lowering"
        trace["normalized_fragment_sha256"] = fingerprint(fragment)
        lowered = adapter(fragment, form, params)
        trace["lowered_fragment_sha256"] = fingerprint(lowered)
        return lowered

    with patch.object(study, "edited_function", edit), patch.object(study, "lower_fragment", lower):
        status, detail, code = study.materialize(tools, task, "gpp_projected", raw)
    stage = trace.pop("stage")
    replay = {
        "checked": status == "pass", "accepted": False,
        "materialization": {"outcome": status, "detail": detail},
        "public": {"outcome": "not_run"}, "heldout": {"outcome": "not_run"},
        "source_sha256": trace,
    }
    if status != "pass":
        replay["first_failure"] = stage
        return replay

    # Score both groups for each checked candidate, even if the public group
    # fails. Both must pass for acceptance, and neither can trigger another edit.
    for group in ("public", "heldout"):
        status, detail = tools.evaluate(task, "gpp", code, task[group], heldout=group == "heldout")
        replay[group] = {"outcome": status, "detail": detail, "cases": len(task[group])}
    first_failure = next((g for g in ("public", "heldout") if replay[g]["outcome"] != "pass"), None)
    replay["first_failure"] = first_failure
    replay["accepted"] = first_failure is None
    return replay


def summary(rows, arm):
    transitions = Counter()
    failures = Counter()
    checked = 0
    for row in rows:
        original = row["original"]["accepted"]
        replay = row[arm]
        checked += replay["checked"]
        transitions[original, replay["accepted"]] += 1
        if not replay["accepted"]:
            failures[replay["first_failure"]] += 1
    return {
        "total": len(rows), "original_accepted": sum(r["original"]["accepted"] for r in rows),
        "projected_checked": checked, "projected_accepted": sum(r[arm]["accepted"] for r in rows),
        "accepted_by_both": transitions[True, True], "only_original": transitions[True, False],
        "only_projection": transitions[False, True], "accepted_by_neither": transitions[False, False],
        "first_failure_counts": dict(sorted(failures.items())),
    }


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--input", type=Path, default=study.HERE / "results/infill.jsonl")
    cli.add_argument("--output", type=Path, default=study.HERE / "results/projection-replay.json")
    cli.add_argument("--gpp", type=Path, default=ROOT / "target/debug/gpp")
    args = cli.parse_args()
    if args.output.resolve() == args.input.resolve():
        cli.error("input and output paths must differ")
    blob = args.input.read_bytes()
    manifest, archived = validate_log(blob)
    verify_sources(manifest, args.gpp)
    from replication_tasks import TASKS
    import scalar_builtins

    tasks = {t["id"]: t for t in TASKS}
    if set(tasks) != set(manifest["tasks"]):
        raise ValueError("task corpus differs from the v3 roster")
    product_path = Path(scalar_builtins.__file__).resolve()
    product_sha = sha(product_path.read_bytes())
    tools = study.Tools(ROOT, args.gpp)
    tools.canaries()
    rows = []
    for source, task_id in product(SOURCES, manifest["tasks"]):
        task, record = tasks[task_id], archived[source, task_id]
        terminal = record["attempts"][-1]
        response = terminal["response"]
        rows.append({
            "source_condition": source, "task": task_id, "model": record["model"],
            "seed": record["seed"], "final_attempt_number": len(record["attempts"]),
            "raw_response_sha256": fingerprint(response),
            "original": {"accepted": record["accepted"], "terminal_outcome": terminal["outcome"],
                         "public_outcome": terminal["public_outcome"], "public_detail": terminal["public_detail"],
                         "heldout_detail": record["heldout_detail"]},
            FROZEN: projected(tools, task, response, study.lower_fragment),
            EXTENDED: projected(tools, task, response, scalar_builtins.lower_fragment),
        })
    verify_sources(manifest, args.gpp)
    if sha(product_path.read_bytes()) != product_sha or blob != args.input.read_bytes():
        raise ValueError("adapter or archived responses changed during replay")
    totals = {source: {arm: summary([r for r in rows if r["source_condition"] == source], arm)
                       for arm in (FROZEN, EXTENDED)} for source in SOURCES}
    report = {
        "study": "Post-hoc projection of final v3 Python-syntax completions",
        "method": "Use the exact final reply from every assigned python_fim and gpp_projected trial. "
                  "Use the archived candidate extraction, compiler, and oracles. For each projection, "
                  "run both test groups once when the candidate checks. Keep every failure. "
                  "The extended arm changes only the scalar lowerer. No model calls or cost estimates.",
        "input_sha256": sha(blob), "replay_script_sha256": sha(Path(__file__).read_bytes()),
        "gpp_sha256": manifest["gpp_sha256"], "frozen_file_sha256": manifest["file_sha256"],
        "extended_file_sha256": {str(product_path.relative_to(ROOT)): product_sha,
                                 "tools/scalar_fragment.py": manifest["file_sha256"]["tools/scalar_fragment.py"]},
        "totals": totals,
        "frozen_gpp_projected_acceptance_disagreements": [
            r["task"] for r in rows if r["source_condition"] == "gpp_projected"
            and r["original"]["accepted"] != r[FROZEN]["accepted"]
        ],
        "results": rows,
    }
    encoded = json.dumps(report, indent=2, ensure_ascii=False) + "\n"
    with TemporaryDirectory(dir=args.output.parent) as work:
        staged = Path(work) / "report.json"
        staged.write_text(encoded, encoding="utf-8")
        staged.replace(args.output)
    print(json.dumps(totals, indent=2))


if __name__ == "__main__":
    main()
