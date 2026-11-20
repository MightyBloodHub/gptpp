"""Get a necessary target result from an unchanged, checked GPT++ caller."""

import json
import subprocess


def public_obligation(binary, source, caller, target, arguments, expected):
    """Return one target-level public example, or None for an unsupported caller."""
    process = subprocess.run(
        [
            binary,
            str(source),
            "--caller",
            caller,
            "--target",
            target,
            "--expect",
            str(expected),
            "--",
            *arguments,
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if process.returncode:
        raise ValueError(f"Caller analysis failed: {process.stderr.strip()}")
    record = json.loads(process.stdout)
    if record.get("status") == "unsupported":
        return None
    if (
        record.get("status") != "exact"
        or record.get("target") != target
        or type(record.get("expected")) is not int
        or not isinstance(record.get("args"), list)
        or any(type(arg) not in (int, bool) for arg in record["args"])
    ):
        raise ValueError(f"Malformed caller analysis result: {record!r}")
    return record


def obligation_text(record):
    args = ", ".join(str(v).lower() for v in record["args"])
    return f"The failed public caller requires {record['target']}({args}) = {record['expected']}."
