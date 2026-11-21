"""Re-execute the frozen public collector with a closed archive as its only model transport."""

import argparse
from io import StringIO
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from unittest.mock import patch

import study


CLOCKS = {"seconds", "model_seconds", "tool_seconds", "elapsed_seconds", "wall_seconds", "audit_wall_seconds"}
# Compiler diagnostic strings include a fresh TemporaryDirectory. Keep the source
# filename, line, column, diagnostic code and message, which must all reproduce.
SCRATCH = re.compile(r"^.*?/gpp-accept-[A-Za-z0-9_-]+/(?=(?:public\.gpp|edit\.expr|candidate\.gpp):)")


def stable(value, field=None):
    if isinstance(value, dict):
        return {k: stable(v, k) for k, v in value.items() if k not in CLOCKS}
    if isinstance(value, (list, tuple)):
        return [stable(v) for v in value]
    if field in {"reason", "diagnostic", "detail"} and isinstance(value, str):
        return SCRATCH.sub("", value)
    return value


def require_equal(actual, expected, context):
    # Preserve the JSON distinction between booleans and integers.
    if json.dumps(actual, sort_keys=True) != json.dumps(expected, sort_keys=True):
        raise ValueError(f"Replay diverged in {context}")


def rerun(calls, operation, context):
    """Replay original request order and compare every regenerated call receipt."""
    pending = iter(calls)

    def cached(port, endpoint, request):
        row = next(pending, None)
        if endpoint != "generate" or row is None:
            raise ValueError(f"Unexpected {endpoint} request during {context}")
        require_equal(request, row["prompt"], f"{context} request")
        return dict(done=True, response=row["response"], prompt_eval_count=row["input_tokens"],
                    eval_count=row["output_tokens"], done_reason=row.get("stop"))

    output = StringIO()
    with patch.object(study, "ollama", cached):
        result = operation(output)
    regenerated = [json.loads(line) for line in output.getvalue().splitlines()]
    require_equal(stable(regenerated), stable(calls), f"{context} call receipts")
    return result


def replay(directory):
    freeze = study.verify_freeze()
    path = directory / "decisions.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    roster = study.roster()
    if not rows or rows[-1].get("kind") != "closed" or rows[-1]["count"] != len(roster):
        raise ValueError("Replay requires a closed decisions.jsonl with the full assignment count")
    records = iter(rows)

    def take(kind):
        row = next(records, {})
        if row.get("kind") != kind:
            raise ValueError(f"Expected {kind} record, found {row.get('kind')!r}")
        return row

    manifest = take("manifest")
    identities = dict(freeze_sha256=study.digest(study.MANIFEST), binary_sha256=study.digest(study.BINARY),
                      model=study.MODEL, model_digest=study.MODEL_DIGEST,
                      assignments=len(roster), prep=freeze["preparation"])
    require_equal({key: manifest[key] for key in identities}, identities, "manifest")
    audits = [take("preparation_call") for _ in study.TASKS]
    captured = take("preflight")
    calls_replayed = 0
    with TemporaryDirectory(prefix="checked-replay-") as directory:
        work = Path(directory)
        checks = study.preflight(work)
        audit, wall = rerun(audits, lambda store: study.mutation_audit(work, 0, store), "preparation")
        regenerated = dict(kind="preflight", results=checks, mutation_audit=audit, audit_wall_seconds=wall)
        require_equal(stable(regenerated), stable(captured), "public preflight and mutation audit")
        for task, lang, arm in roster:
            key = "/".join((task.name, lang, arm))
            calls = []
            row = next(records, {})
            while row.get("kind") == "call":
                require_equal(row["trial"], key, "call roster")
                calls.append(row)
                row = next(records, {})
            require_equal([row.get("kind"), row.get("trial")], ["trial", key], "assignment roster")
            with TemporaryDirectory(dir=work) as temp:
                def execute(store):
                    return study.trial(task, lang, arm, Path(temp), store, 0)
                actual = rerun(calls, execute, key)
            require_equal(stable(actual), stable(row), key)
            calls_replayed += len(calls)
    take("closed")
    if next(records, None) is not None:
        raise ValueError("Unexpected records after the closed roster")
    return dict(kind="offline_public_replay", decisions_sha256=study.digest(path), trials=len(roster),
                archived_preparation_calls=len(audits), archived_trial_calls=calls_replayed, new_model_calls=0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, help="closed run containing decisions.jsonl")
    print(json.dumps(replay(parser.parse_args().directory), indent=2))
