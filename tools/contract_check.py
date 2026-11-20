"""Read a finite verification result for an exact checked file."""

from hashlib import sha256
import json

import propose


def verify(binary, path, budget):
    result = propose.compiler(binary, "verify", path, "--format=json", "--budget", budget)
    status = {0: "passed", 1: "counterexample", 3: "incomplete"}.get(result.returncode)
    if status is None or not result.stdout:
        raise propose.ProposalError(result.stderr.decode(errors="replace").strip() or "Verifier failed.")
    report = json.loads(result.stdout)
    revision = "sha256:" + sha256(path.read_bytes()).hexdigest()
    if (report.get("schema") != "gpp.verify/1" or report.get("status") != status
            or report.get("revision") != revision):
        raise ValueError("Unexpected verifier status, schema or source revision.")
    if status == "passed" and not (report.get("contracts") and report.get("checked", 0) > 0):
        raise ValueError("Verifier passed without checking a contract.")
    return report


def witness(report):
    row = next(c for c in report["contracts"] if c["status"] == "counterexample")
    return {"contract": row["name"], **row["counterexample"]}
