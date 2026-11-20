"""Replay the two frozen expression studies, verifying process-specific Rust diagnostics."""

from collections import deque
from hashlib import sha256
import json
import re
from unittest.mock import patch

import catalog_study as followup
import run_expression as base
from bench.expression.tasks import TASKS

# Rust inserts a fresh OS thread number into some embedded error messages. A
# retry saw the historical number. Restore it only after checking all other
# bytes of the freshly produced diagnostic and the category of the failure.
RUST_THREAD = re.compile(r"(?<=thread 'main' )\([0-9]+\)(?= (?:panicked at|has overflowed its stack))")


def replay_with_diagnostics(language, recorded_details, action):
    expected = deque(d for d in recorded_details if RUST_THREAD.search(d))
    if not expected:
        action()
        return 0
    if language != "rust":
        raise ValueError("Unexpected Rust thread ID in another language's result.")
    evaluator = base.prior.previous.public_evaluate
    count = len(expected)

    def evaluate(*args, **kwargs):
        status, detail, entry = evaluator(*args, **kwargs)
        if status == "runtime_error" and RUST_THREAD.search(detail):
            archived = expected.popleft()
            if RUST_THREAD.sub("(thread)", detail) != RUST_THREAD.sub("(thread)", archived):
                raise ValueError(f"Rust runtime diagnostic changed: {detail}")
            detail = archived
        return status, detail, entry

    with patch.object(base.prior.previous, "public_evaluate", evaluate):
        action()
    if expected:
        raise ValueError("A recorded Rust runtime diagnostic was missing.")
    return count


def main():
    config = followup.config()  # Checks both executables and all frozen scorer source files.
    meta, rows = followup.read(followup.DATA)
    archive = base.HERE / "results/catalog.jsonl"
    follow_meta, follow_rows = followup.read(archive)
    if config != follow_meta:
        raise ValueError("Follow-up manifest changed.")
    fingerprint = sha256(json.dumps(TASKS, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if meta["corpus_sha256"] != fingerprint:
        raise ValueError("Original task content changed.")
    tools = base.prior.Tools(base.ROOT, base.ROOT / "target/debug/gpp")
    tools.canaries()
    restored = 0
    for assignment, row in zip(base.assignments(TASKS), rows, strict=True):
        model, task, arm = assignment
        if (model, task["id"], arm) != (row["model"], row["task"], row["condition"]):
            raise ValueError("Original roster diverged.")
        restored += replay_with_diagnostics(
            row["language"],
            [a.get("public_detail", "") for a in row["attempts"]],
            lambda: base.trial(tools, task, model, arm, meta["model_default_stops"][model], row),
        )
    for assignment, row in zip(followup.assignments(), follow_rows, strict=True):
        model, task, language = assignment
        if (model, task["id"], language) != (row["model"], row["task"], row["language"]):
            raise ValueError("Follow-up roster diverged.")
        restored += replay_with_diagnostics(
            language, [row["detail"]], lambda: followup.trial(tools, *assignment, row)
        )
    print(
        f"Replayed {len(rows)} original trials ({sum(len(r['attempts']) for r in rows)} calls) and "
        f"{len(follow_rows)} catalog trials. Verified {restored} Rust diagnostics with variable thread IDs."
    )


if __name__ == "__main__":
    main()
