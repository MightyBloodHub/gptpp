"""Run, replay or report the example-filtered repair CLI development study."""

import argparse
from contextlib import contextmanager
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import platform
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import time

import run_expression as base
from bench.expression.tasks import TASKS
from evaluate_project import ENTRY, MODULE, evaluate, source_for
from propose import ollama

HERE, ROOT = base.HERE, base.ROOT
CATALOG = HERE / "results/catalog.jsonl"
GPP = ROOT / "target/debug/gpp"
CLI = ROOT / "tools/repair.py"


def fingerprint(data):
    return sha256(data).hexdigest()


def read_archive(path):
    with path.open() as stream:
        return json.loads(next(stream)), [json.loads(line) for line in stream]


def baseline():
    meta, records = read_archive(CATALOG)
    rows = [r for r in records if r["language"] == "gpp"]
    expected = {(model, t["id"]) for model in meta["model_digests"] for t in TASKS}
    if len(rows) != len(expected) or {(r["model"], r["task"]) for r in rows} != expected:
        raise ValueError("The archived GPT++ catalog roster is incomplete.")
    return meta, rows


def source_hashes():
    files = [
        CLI, *(ROOT / "src" / name for name in (
            "check.rs", "edit.rs", "interpreter.rs", "ir.rs", "main.rs", "native.rs",
            "syntax.rs", "trace.rs", "bootstrap.c",
        )), HERE / "repair-protocol.md",
        Path(__file__).resolve(), HERE / "tasks.py", HERE.parent / "policy/fresh.py",
        HERE.parent / "maintenance/evaluate_project.py", HERE.parent / "empirical/evaluate.py",
        # Include the optional authoring modules imported by the product and scorer.
        *(ROOT / "tools" / name for name in (
            "propose.py", "caller_context.py", "obligation_feedback.py",
            "policy_ir.py", "scalar_builtins.py", "scalar_fragment.py",
        )),
    ]
    return {str(p.relative_to(ROOT)): fingerprint(p.read_bytes()) for p in files}


def live_metadata(port, meta):
    available = {m["name"]: m for m in ollama(port, "tags")["models"]}
    models = {}
    for model, digest in meta["model_digests"].items():
        entry = available[model]
        if entry["digest"] != digest:
            raise ValueError(f"Model fingerprint differs for {model}.")
        show = ollama(port, "show", {"model": model})
        models[model] = {
            "tag": {k: entry[k] for k in ("name", "digest", "remote_model", "remote_host") if k in entry},
            "show": {k: show[k] for k in ("template", "parameters", "remote_model", "remote_host") if k in show},
        }
    return {"ollama": ollama(port, "version")["version"], "models": models}


@contextmanager
def transport(model, info, port, saved):
    """Relay one real generation or return its complete saved Ollama reply on replay."""
    calls, errors = [], []

    class Handler(BaseHTTPRequestHandler):
        def dispatch(self, payload):
            try:
                if self.path == "/api/tags" and payload is None:
                    data = {"models": [info["tag"]]}
                elif self.path == "/api/show" and payload == {"model": model}:
                    data = info["show"]
                elif self.path == "/api/generate" and payload["model"] == model and not calls:
                    if saved is None:
                        started = time.monotonic()
                        reply = ollama(port, "generate", payload)
                        elapsed = round((time.monotonic() - started) * 1000)
                    else:
                        call, = saved
                        if payload != call["request"]:
                            raise ValueError("Inference payload differs from archive.")
                        reply, elapsed = call["reply"], call["round_trip_ms"]
                    if reply.get("done") is not True or not isinstance(reply.get("response"), str):
                        raise ValueError("Incomplete generation.")
                    if not all(type(reply.get(k)) is int for k in ("prompt_eval_count", "eval_count")):
                        raise ValueError("Ollama did not report token usage.")
                    calls.append({"request": payload, "reply": reply, "round_trip_ms": elapsed})
                    data = reply
                else:
                    raise ValueError(f"Unexpected request to {self.path}.")
            except Exception as exc:
                errors.append(exc)
                self.send_error(500)
                return
            raw = json.dumps(data).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            self.dispatch(None)

        def do_POST(self):
            self.dispatch(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))

        def log_message(self, *_):
            pass

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01})
        thread.start()
        try:
            yield server.server_port, calls
        finally:
            server.shutdown()
            thread.join()
    if errors:
        raise errors[0]


def score(tools, task, file, revision, candidate, fragment):
    """Apply the checked edit to a private preview; the scorer exclusively owns heldout."""
    a, b = candidate["start_byte"], candidate["end_byte"]
    if file.read_bytes()[a:b].decode() != candidate["old"]:
        raise ValueError("Published span does not name its advertised expression.")
    if fragment.read_text() != candidate["replacement"] + "\n":
        raise ValueError("Published fragment differs from the model's selection.")
    patched = subprocess.check_output(
        [GPP, "edit", file, "--function", task["target"], "--expect", revision, "--at", f"{a}:{b}",
         "--expr", fragment, "--stdout"], text=True, timeout=15,
    )
    if not patched.startswith(MODULE) or not patched.endswith(ENTRY):
        raise ValueError("Protected module envelope changed.")
    source = patched[len(MODULE):-len(ENTRY)]
    public, detail = evaluate(tools, "gpp", source, task["public"])
    if public != "pass":
        raise ValueError(f"Public examples rejected the offered candidate: {detail}")
    status, detail = evaluate(tools, "gpp", source, task["heldout"])
    return {"patch_sha256": fingerprint(patched.encode()), "public": public,
            "outcome": "accepted" if status == "pass" else "heldout_" + status, "detail": detail}


def trial(tools, task, model, meta, port, saved=None):
    original = MODULE + source_for(task, "gpp") + ENTRY
    with TemporaryDirectory(prefix="gpp-repair-study-") as directory:
        work = Path(directory)
        file, cases, frag = work / "base.gpp", work / "public.json", work / "selected.expr"
        file.write_text(original)
        cases.write_text(json.dumps([dict(function=fn, args=args, expected=value)
                                     for fn, args, value in task["public"]]))
        with transport(model, meta["models"][model], port, None if saved is None else saved["calls"]) as (local, calls):
            start = time.monotonic()
            process = subprocess.run(
                [sys.executable, "-B", CLI, file, "--function", task["target"], "--task", task["description"],
                 "--cases", cases, "--model", model, "--port", str(local), "--gpp", GPP, "-o", frag],
                capture_output=True, text=True, timeout=300,
            )
            wall_ms = round((time.monotonic() - start) * 1000)
        if process.returncode:
            raise ValueError(f"Repair CLI failed: {process.stderr or process.stdout}")
        result = json.loads(process.stdout)
        product = {k: result[k] for k in ("schema", "revision", "function", "status", "tested",
                                          "budget", "exhausted", "candidates", "selected")}
        menu, choice, status = product["candidates"], product["selected"], product["status"]
        if len(calls) != int(bool(menu)):
            raise ValueError("Expected exactly one selector call for every nonempty menu.")
        if file.read_text() != original or product["function"] != task["target"]:
            raise ValueError("Repair CLI changed its input or mislabeled the target.")
        if status == "selected":
            if type(choice) is not int or not 1 <= choice <= len(menu):
                raise ValueError("Published an invalid menu ID.")
            selected = score(tools, task, file, product["revision"], menu[choice - 1], frag)
        else:
            if (status not in ("abstained", "already_passes", "no_candidates") or frag.exists()
                    or choice is not None or (status == "abstained") != bool(menu)):
                raise ValueError(f"Inconsistent CLI outcome: {status}")
            selected = {"outcome": status}
        control = {"outcome": "no_candidates"}
        if menu:
            if choice == 1:
                control = selected
            else:
                first = work / "first.expr"
                first.write_text(menu[0]["replacement"] + "\n")
                control = score(tools, task, file, product["revision"], menu[0], first)
        row = {"model": model, "task": task["id"], "public_cases": len(task["public"]),
               "withheld_cases": len(task["heldout"]), "product": product, "calls": calls,
               "selected": selected, "first_candidate": control,
               "cli_wall_ms": wall_ms if saved is None else saved["cli_wall_ms"]}
        if saved is not None and saved != row:
            raise ValueError(f"Recorded outcome differs for {model}/{task['id']}.")
        return row


def verify_rows(rows, comparator):
    if [(r["task"], r["model"]) for r in rows] != [(r["task"], r["model"]) for r in comparator]:
        raise ValueError("Expected one trial per archived GPT++ catalog row in its original order.")


def run(path, replay, port):
    meta, comparator = baseline()
    common = {"study": "example-filtered-repair-v1", "baseline_sha256": fingerprint(CATALOG.read_bytes()),
              "sources": source_hashes(), "task_sha256": fingerprint(json.dumps(TASKS, sort_keys=True).encode())}
    if replay:
        archive, records = read_archive(path)
        verify_rows(records, comparator)
        if any(archive.get(k) != v for k, v in common.items()):
            raise ValueError("Study source, fixture or baseline fingerprint changed.")
    else:
        archive = {**common, **live_metadata(port, meta), "compiler_sha256": fingerprint(GPP.read_bytes()),
                   "platform": platform.platform(), "python": platform.python_version()}
        records = []
    tasks = {t["id"]: t for t in TASKS}
    tools = base.prior.Tools(ROOT, GPP)
    if replay:
        for r in records:
            trial(tools, tasks[r["task"]], r["model"], archive, None, r)
        print(f"Replayed {len(records)} CLI runs and verified every model request, menu and scored patch.")
    else:
        with path.open("x", buffering=1) as stream:
            print(json.dumps(archive), file=stream)
            for baseline_row in comparator:
                model, task = baseline_row["model"], tasks[baseline_row["task"]]
                row = trial(tools, task, model, archive, port)
                print(json.dumps(row), file=stream)
                print(model, task["id"], row["selected"]["outcome"], flush=True)


def report(path):
    archive, rows = read_archive(path)
    _, comparator = baseline()
    if archive["baseline_sha256"] != fingerprint(CATALOG.read_bytes()):
        raise ValueError("Catalog baseline fingerprint changed.")
    verify_rows(rows, comparator)
    print("# Example-filtered GPT++ expression repairs\n")
    print("Each pinned model attempted the same three development tasks. A selected edit must pass all "
          "public and withheld checks. The first-candidate control applies menu item 1 without inference.\n")
    print("| Model | Task | Candidates tested | Menu size | Choice | Withheld outcome | First candidate |")
    print("|---|---|---:|---:|---:|---|---|")
    for r in rows:
        p = r["product"]
        print(f"| {r['model']} | {r['task']} | {p['tested']} | {len(p['candidates'])} | "
              f"{p['selected'] or '—'} | {r['selected']['outcome']} | {r['first_candidate']['outcome']} |")
    print("\n| Model | Workflow | Accepted | Model calls | Input tokens | Output tokens | Tokens/accept |")
    print("|---|---|---:|---:|---:|---:|---:|")
    for model in archive["models"]:
        group = [r for r in rows if r["model"] == model]
        original = [r for r in comparator if r["model"] == model]
        for name, passes, replies in [
            ("Archived catalog", sum(r["outcome"] == "accepted" for r in original), [r["reply"] for r in original]),
            ("Example-filtered menu", sum(r["selected"]["outcome"] == "accepted" for r in group),
             [c["reply"] for r in group for c in r["calls"]]),
            ("First candidate", sum(r["first_candidate"]["outcome"] == "accepted" for r in group), []),
        ]:
            inputs = sum(r["prompt_eval_count"] for r in replies)
            outputs = sum(r["eval_count"] for r in replies)
            ratio = f"{(inputs + outputs) / passes:,.1f}" if passes else "undefined"
            print(f"| {model} | {name} | {passes}/{len(group)} | {len(replies)} | {inputs:,} | "
                  f"{outputs:,} | {ratio} |")
    abstained = sum(r["selected"]["outcome"] == "abstained" for r in rows)
    empty = sum(r["selected"]["outcome"] == "no_candidates" for r in rows)
    refuted = sum(r["selected"]["outcome"].startswith("heldout_") for r in rows)
    print(f"\nAcross {len(rows)} trials the search yielded {empty} empty menus. The models abstained "
          f"{abstained} times. Withheld checks refuted {refuted} selected edits that passed the public examples.")
    for r in rows:
        if r["selected"].get("detail"):
            print(f"\n- {r['model']}, {r['task']}. {r['selected']['detail']}")
    wall = sum(r["cli_wall_ms"] for r in rows)
    inference = sum(c["round_trip_ms"] for r in rows for c in r["calls"])
    exhausted = sum(r["product"]["exhausted"] for r in rows)
    print(f"\nThe repair CLI used {wall / 1000:.2f} seconds across all trials, including {inference / 1000:.2f} "
          f"seconds in model generation requests. {exhausted}/{len(rows)} searches reached the candidate "
          "budget before exhausting the grammar. Timing depends on the host and model cache. The scorer ran "
          "after each timed CLI invocation.")
    print("\nThe three project extracts were previously used for development. The archived catalog generated "
          "its own replacement string. The new tool spends deterministic search time building the choices. "
          "Both models draw from the same menu for a given task. A language-wide cost advantage, the value "
          "of a model over deterministic ordering on new tasks, and performance against comparable Python "
          "or Rust search remain open.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--replay", action="store_true")
    action.add_argument("--report", action="store_true")
    parser.add_argument("--port", type=int, default=11434)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    if args.report:
        report(args.archive)
    else:
        run(args.archive, args.replay, args.port)
