"""Replay the three GPT++ expression arms through the real proposal CLI without inference."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys
from tempfile import TemporaryDirectory

from run_expression import ROOT, prior
from bench.expression.tasks import TASKS
from evaluate import arguments
from evaluate_project import ENTRY, MODULE, functions, source_for
from test_propose import mock_ollama


ARMS = ("gpp_given", "gpp_locate", "gpp_combined")
CLI = ROOT / "tools/propose.py"
GPP = ROOT / "target/debug/gpp"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def caller_excerpt(source, target):
    records = [fn.record() for fn in functions(source, "gpp").values()]
    excerpt = prior.maintenance.caller_context(records, target, "gpp")
    return "".join(f"// {line}\n" for line in excerpt.splitlines())


def check_request(actual, saved, row, source, dump, target):
    prompt, suffix = saved["prompt"], saved["suffix"]
    model = row["model"]
    expected = dict(model=model, stream=False, keep_alive="3m", options=saved["sampling"])
    if model == "starcoder2:3b":
        expected["raw"] = True
        prompt = "<fim_prefix>" + prompt + "<fim_suffix>" + suffix + "<fim_middle>"
    else:
        expected["suffix"] = suffix
    expected["prompt"] = prompt
    if actual == expected:
        return False
    # The CLI obtains caller excerpts from the compiler AST dump. The scored
    # experiment obtains them from the original source. Accept only this exact
    # substitution on retries; all other text and wire settings must match.
    if saved["stage"] == "retry":
        original = caller_excerpt(source, target)
        canonical = caller_excerpt(dump.split("\n", 1)[1], target)
        if original != canonical and original and prompt.count(original) == 1:
            expected["prompt"] = prompt.replace(original, canonical)
            if actual == expected:
                return True
    differing = [key for key in set(actual) | set(expected) if actual.get(key) != expected.get(key)]
    raise ValueError(f'{saved["stage"]} request differs in {differing}')


def hidden_outcome(patch, cases, work):
    trial = work / "hidden.gpp"
    for name, args, expected in cases:
        call = f"{name}({arguments(args, 'gpp')})"
        trial.write_text(MODULE + patch + f"\npub fn main() -> I64 !{{}} {{ return {call}; }}\n")
        proc = subprocess.run([GPP, "run", "--interpreter", "--fuel", "1000000", trial],
                              capture_output=True, text=True, timeout=15)
        if proc.returncode:
            require("fault:" in proc.stderr, f"Held-out harness failed: {proc.stderr}")
            return "heldout_runtime_error"
        if int(proc.stdout) != expected:
            return "heldout_wrong_answer"
    return "accepted"


def replay_row(manifest, task, row):
    target, arm, model = task["target"], row["condition"], row["model"]
    source = source_for(task, "gpp")
    saved = row["attempts"]
    with TemporaryDirectory(prefix="gpp-product-replay-") as directory:
        work = Path(directory)
        file, cases, output = work / "base.gpp", work / "public.json", work / "change.expr"
        file.write_text(MODULE + source + ENTRY)
        cases.write_text(json.dumps([dict(function=fn, args=a, expected=e) for fn, a, e in task["public"]]))
        listing = json.loads(subprocess.check_output([GPP, "expressions", file, "--function", target]))
        original_dump = subprocess.check_output([GPP, "ast", file], text=True)
        base = listing["revision"]
        if arm == "gpp_given":
            matches = [expr for expr in listing["expressions"] if expr["text"] == task["site"]["gpp"]]
            require(len(matches) == 1, "Given site no longer unique")
            chosen = matches[0]
            at = f'{chosen["start_byte"]}:{chosen["end_byte"]}'
            scope = ["--at", at, "--expect", base]
        else:
            scope = ["--locate", "combined" if arm == "gpp_combined" else "separate"]
        stops = "\n".join("stop " + json.dumps(stop) for stop in manifest["model_default_stops"][model])
        with mock_ollama([r["response"] for r in saved], model_name=model,
                         digest=manifest["model_digests"][model], parameters=stops,
                         infill=model != "starcoder2:3b") as (port, calls):
            proc = subprocess.run(
                [sys.executable, "-B", CLI, file, "--function", target, "--task", task["description"],
                 "--maintenance", *scope, "--cases", cases, "--model", model, "--gpp", GPP,
                 "--port", str(port), "-o", output], capture_output=True, text=True, timeout=60)
        requests = [request for path, request in calls if path == "/api/generate"]
        require(len(saved) == len(requests), f"Generated {len(requests)} requests, expected {len(saved)}")
        formatted = sum(check_request(request, record, row, source, original_dump, target)
                        for request, record in zip(requests, saved))
        require(file.read_text() == MODULE + source + ENTRY, "Preview changed source")
        span = row["span"]
        selected = re.search(r"^Selected expression (\d+:\d+):", proc.stdout, re.M)
        if span:
            start, end = (listing["start_byte"] + n for n in span)
            expected_at = f"{start}:{end}"
            if arm != "gpp_given":
                require(selected is not None, "CLI did not report the selected expression")
                at = selected.group(1)
            require(at == expected_at, "Selected bytes differ")
        else:
            require(not selected and arm != "gpp_given", "Unexpected expression selection")

        last = saved[-1]
        outcome = last["outcome"]
        published = last.get("public_outcome") == "pass"
        require((proc.returncode == 0) == published and output.exists() == published,
                f"Unexpected CLI publication status: {proc.stderr}")
        if published:
            fragment = last["fragment"] if last["stage"] == "change" else last["response"]
            require(output.read_text() == fragment.strip() + "\n", "Published fragment differs")
            command = [str(GPP), "edit", str(file), "--function", target, "--at", expected_at,
                       "--expr", str(output), "--expect", base]
            require(shlex.split(proc.stdout.splitlines()[-1]) == command, "Apply command differs")
            subprocess.run(command, capture_output=True, check=True, timeout=15)
            patched = file.read_text()
            require(patched.startswith(MODULE) and patched.endswith(ENTRY), "Module envelope changed")
            body = patched[len(MODULE):-len(ENTRY)]
            require(sha256(body.encode()).hexdigest() == last["patch_sha256"], "Patch hash differs")
            require(hidden_outcome(body, task["heldout"], work) == outcome, "Held-out outcome differs")
        elif outcome == "selection_error":
            require(span is None and any(msg in proc.stderr for msg in (
                "Location failed:", "Expected one old expression", "must be nonempty")),
                f"Expected selection rejection: {proc.stderr}")
        elif outcome == "check_error":
            require("validation" in proc.stderr and "error[GPP-" in proc.stderr,
                    f"Expected compiler rejection: {proc.stderr}")
        elif outcome in ("runtime_error", "wrong_answer"):
            expected_text = "raised fault:" if outcome == "runtime_error" else " returned "
            entry = last["public_failed_entry"]
            require("validation" in proc.stderr and f": {entry}(" in proc.stderr and expected_text in proc.stderr,
                    f"Expected a public {outcome} from {entry}: {proc.stderr}")
        else:
            raise ValueError(f"Unexpected archived outcome {outcome}")
        require(row["accepted"] == (outcome == "accepted"), "Acceptance differs")
        require(row["first_accepted"] == (row["accepted"] and last["stage"] != "retry"),
                "First-attempt acceptance differs")
    return len(requests), formatted, published


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    with args.archive.open() as stream:
        manifest = json.loads(next(stream))
        rows = [row for line in stream if (row := json.loads(line))["condition"] in ARMS]
    corpus = json.dumps(TASKS, sort_keys=True, separators=(",", ":")).encode()
    require(sha256(corpus).hexdigest() == manifest["corpus_sha256"], "Archived corpus fingerprint differs")
    tasks = {task["id"]: task for task in TASKS}
    wanted = {(model, task, arm) for model in manifest["models"] for task in tasks for arm in ARMS}
    observed = {(row["model"], row["task"], row["condition"]) for row in rows}
    require(observed == wanted and len(rows) == len(wanted), "Incomplete or duplicated GPT++ expression rows")
    for path, digest in [(GPP, manifest["gpp_sha256"]), (CLI, manifest["file_sha256"]["tools/propose.py"])]:
        require(sha256(path.read_bytes()).hexdigest() == digest, f"Archived fingerprint differs for {path}")
    counts = Counter()
    for row in rows:
        label = "/".join([row["model"], row["task"], row["condition"]])
        try:
            requests, formatted, published = replay_row(manifest, tasks[row["task"]], row)
        except ValueError as exc:
            raise SystemExit(f"{label}: {exc}") from exc
        counts.update(rows=1, calls=requests, byte_exact_calls=requests-formatted,
                      canonicalized_caller_calls=formatted, public_pass=int(published),
                      accepted=int(row["accepted"]))
        if formatted:
            print(f"{label}: {formatted} retry with compiler-formatted caller excerpts")
    print(json.dumps(dict(counts), sort_keys=True))


if __name__ == "__main__":
    main()
