"""Supplemental within-assignment replay with the advertised abs helper in GPT++ modules."""

import argparse
from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

import public
import study

HELPER = "fn abs(x: I64) -> I64 !{} { return if x < 0 { -x } else { x }; }"
POLICY = Path(__file__).with_name("matched_protocol.md")
PRIMARY_FREEZE = "93fb2f2fa40d412fe3b606721826d7803d88c0d435cf1cb5c8057663d6d3ac69"


def sketch(task):
    module, code = public.sketch(task).split("\n", 1)
    return f"{module}\n{HELPER}\n{code}"


def pin():
    code_hash = study.digest(Path(__file__))
    if (f"Collector SHA-256 `{code_hash}`" not in POLICY.read_text()
            or study.digest(study.MANIFEST) != PRIMARY_FREEZE):
        raise ValueError("Supplemental collector or frozen source roster changed")
    study.verify_freeze()
    return dict(collector_sha256=code_hash, helper_sha256=sha256(HELPER.encode()).hexdigest(),
                policy_sha256=study.digest(POLICY), freeze_sha256=PRIMARY_FREEZE)


def key(trial, request):
    # JSON serialization preserves distinctions such as false and 0.
    return trial, json.dumps(request, sort_keys=True, separators=(",", ":"), allow_nan=False)


def receipts(directory):
    path = directory / "decisions.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    manifest = rows[0]
    roster = ["/".join((t.name, lang, arm)) for t, lang, arm in study.roster()]
    expected = {"freeze_sha256": PRIMARY_FREEZE, "model": study.MODEL, "model_digest": study.MODEL_DIGEST,
                "assignments": len(roster), "binary_sha256": study.digest(study.BINARY)}
    if (manifest.get("kind") != "manifest" or any(manifest[k] != v for k, v in expected.items())
            or rows[-1].get("kind") != "closed" or rows[-1]["count"] != len(roster)
            or [r["trial"] for r in rows if r["kind"] == "trial"] != roster):
        raise ValueError("Sensitivity requires the complete matching frozen primary ledger")
    cache = defaultdict(list)
    counts = defaultdict(int)
    audit_ids = []
    for line, row in enumerate(rows, 1):
        kind = row["kind"]
        if kind == "unmetered_call":
            raise ValueError("Primary ledger contains an unmetered inference")
        if kind in ("call", "preparation_call"):
            assignment = row["trial"] if kind == "call" else "preparation/" + row["task"]
            cache[key(assignment, row["prompt"])].append((line, row))
            if kind == "preparation_call":
                audit_ids.append(row["task"])
            else:
                counts[assignment] += 1
    if audit_ids != [t.name for t in study.TASKS] or any(counts[r["trial"]] != r["model_calls"]
                                                          for r in rows if r["kind"] == "trial"):
        raise ValueError("Primary request ledger does not match its completed assignments")
    return manifest, cache, study.digest(path)


class Transport:
    def __init__(self, cache, port):
        self.cache = cache
        self.port = port
        self.primary_emit = study.emit
        self.live = study.metered_reply
        self.pinned_model = False
        self.pending = None
        self.calls = defaultdict(list)

    def reply(self, port, request, trial, store, start):
        if self.pending is not None:
            raise RuntimeError("Previous request has no receipt")
        matches = self.cache.get(key(trial, request))
        if matches:
            line, row = matches.pop(0)
            self.pending = (trial, line, row["model_seconds"])
            return dict(response=row["response"], done=True, done_reason=row.get("stop"),
                        prompt_eval_count=row["input_tokens"], eval_count=row["output_tokens"])
        if not self.pinned_model:
            versions = {m["name"]: m["digest"] for m in study.ollama(port, "tags")["models"]}
            if versions.get(study.MODEL) != study.MODEL_DIGEST:
                raise ValueError("Pinned Qwen is required for a changed model request")
            self.pinned_model = True
        self.pending = (trial, None, None)
        return self.live(port, request, trial, store, start)

    def emit(self, store, row):
        if row["kind"] in ("call", "preparation_call"):
            trial, line, charged_seconds = self.pending
            actual_id = row.get("trial") or "preparation/" + row["task"]
            if actual_id != trial:
                raise RuntimeError("Inference receipt does not match the active assignment")
            physical = line is None
            row.update(provenance="live_model" if physical else "same_request_replay", primary_line=line,
                       physical_model_seconds=row["model_seconds"] if physical else 0.0,
                       physical_input_tokens=row["input_tokens"] if physical else 0,
                       physical_output_tokens=row["output_tokens"] if physical else 0)
            if not physical:
                row["model_seconds"] = charged_seconds
            self.calls[trial].append(row.copy())
            self.pending = None
        self.primary_emit(store, row)


def collect(primary, output, port):
    policy = pin()
    manifest, cache, primary_hash = receipts(primary)
    output.mkdir(parents=True, exist_ok=False)
    transport = Transport(cache, port)
    with TemporaryDirectory(prefix="matched-helpers-") as directory, (output / "decisions.jsonl").open("x") as store:
        work = Path(directory)
        study.emit(store, dict(manifest, started_utc=study.utc(), provenance="matched-helper sensitivity",
                               primary_decisions_sha256=primary_hash, supplement=policy))
        with patch.object(study, "sketch", sketch), patch.object(study, "metered_reply", transport.reply), \
                patch.object(study, "emit", transport.emit):
            calibrated = study.preflight(work)
            audit, audit_wall = study.mutation_audit(work, port, store)
            replay_s = 0.0
            for row in audit:
                charged, = transport.calls["preparation/" + row["task"]]
                row.update({k: charged[k] for k in ("model_seconds", "physical_model_seconds", "provenance",
                                                    "physical_input_tokens", "physical_output_tokens", "primary_line")})
                replay_s += charged["model_seconds"] - charged["physical_model_seconds"]
            study.emit(store, dict(kind="preflight", results=calibrated, mutation_audit=audit,
                                   physical_audit_wall_seconds=audit_wall, audit_wall_seconds=audit_wall + replay_s))
            for task, lang, arm in study.roster():
                with TemporaryDirectory(dir=work) as scratch:
                    row = study.trial(task, lang, arm, Path(scratch), store, port)
                calls = transport.calls[row["trial"]]
                physical_model = sum(r["physical_model_seconds"] for r in calls)
                physical_wall = row["wall_seconds"]
                tools = physical_wall - physical_model
                row.update(provenance="matched-helper sensitivity", physical_wall_seconds=physical_wall,
                           physical_model_calls=sum(r["provenance"] == "live_model" for r in calls),
                           physical_model_seconds=physical_model, tool_seconds=tools,
                           wall_seconds=tools + row["model_seconds"])
                study.emit(store, row)
                print(row["trial"], row["decision"], flush=True)
            study.emit(store, dict(kind="closed", ended_utc=study.utc(), count=len(study.roster())))
    subprocess.run([sys.executable, "-B", __file__, "score", output], check=True)


def score_closed(output):
    # The collector process never imports the sealed evaluator. The frozen
    # scorer validates all 90 decisions, publishes scores, and invokes report.py.
    rows = [json.loads(line) for line in (output / "decisions.jsonl").read_text().splitlines()]
    if rows[-1].get("kind") != "closed" or rows[0].get("supplement") != pin():
        raise ValueError("A matching closed sensitivity ledger is required for scoring")
    import score
    with patch.object(score, "sketch", sketch):
        score.main(output)
    results = output / "results.md"
    body = results.read_text().replace("# Fresh paired comparison", "## Paired outcomes", 1)
    body = body.replace("six newly executed assignments", "six supplemental assignments")
    lines = ["# Matched-helper sensitivity", "",
             "These are the pilot’s six families rechecked with the advertised `abs` helper available in the GPT++ sketch. Each model request reused its primary receipt only on an exact request match within the same assignment. Changed requests used live Qwen. This supplemental comparison cannot qualify the workflow on fresh families.", "",
             "| Stage | Replayed calls | Live calls | Attributed input/output | Physical input/output | Attributed model s | Physical model s |", "|---|---:|---:|---:|---:|---:|---:|"]
    for label, subset in [("Preparation", ("preparation_call",)), ("Trial", ("call",)),
                          ("Total", ("preparation_call", "call"))]:
        calls = [r for r in rows if r["kind"] in subset]
        live = sum(r["provenance"] == "live_model" for r in calls)
        def total(k):
            return sum(r[k] for r in calls)
        lines.append(f"| {label} | {len(calls)-live} | {live} | {total('input_tokens'):,}/{total('output_tokens'):,} | {total('physical_input_tokens'):,}/{total('physical_output_tokens'):,} | {total('model_seconds'):.2f} | {total('physical_model_seconds'):.2f} |")
    lines.extend(["", "The outcomes table charges the original measured input, output and model time for reused replies. Public compiler work and sealed scoring ran again. Each `primary_line` points to the reused prompt and reply in the primary ledger whose SHA-256 is in this run’s manifest.", "", body])
    results.write_text("\n".join(lines))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    run = sub.add_parser("run")
    run.add_argument("primary", type=Path)
    run.add_argument("output", type=Path)
    run.add_argument("--port", type=int, default=11434)
    sub.add_parser("score").add_argument("output", type=Path)
    args = parser.parse_args()
    if args.operation == "run":
        collect(args.primary, args.output, args.port)
    else:
        score_closed(args.output)
