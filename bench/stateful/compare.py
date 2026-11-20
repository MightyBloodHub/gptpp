"""Collect, replay and report a matched state-transition maintenance benchmark."""

import argparse
from hashlib import sha256
from itertools import islice
import json
from pathlib import Path
import platform
import random
import shutil
import sys
from tempfile import TemporaryDirectory
import time

import adapters as a
from tasks import TASKS, oracle, withheld

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "Cargo.toml").is_file())
sys.path.insert(0, str(ROOT / "tools"))
from propose import ollama  # noqa: E402


MODELS = {
    "qwen2.5-coder:7b": "dae161e27b0e90dd1856c8bb3209201fd6736d8eb66298e75ed87571486f4364",
    "starcoder2:3b": "f67ae0f64584a4d1d7c609bf4778dd0d07054582362d21ca4f0eddea22aafd0c",
}


def digest(data):
    return sha256(data).hexdigest()


def ms(start):
    return round((time.monotonic() - start) * 1000)


def write(store, row):
    print(json.dumps(row, ensure_ascii=False), file=store, flush=True)


def read(path):
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    return rows[0], rows[1:]


def roster():
    for model in MODELS:
        order = [(t, language) for t in TASKS for language in a.LANGUAGES]
        random.Random(61213).shuffle(order)
        for t, language in order:
            yield model, t, language


def prompt(model, task, lang, previous):
    lines = [
        f"Change one scalar expression in this { {'gpp': 'GPT++', 'rust': 'Rust', 'python': 'typed Python'}[lang] } state machine.",
        task.request,
        "Original expression to be replaced: " + a.expr(lang, task.old),
        "The ?change slot is the only editable expression. Its type is " + task.result_type + ".",
        a.source(lang, task),
        "The machine starts in "
        + str(list(task.initial))
        + ". The visible sequence contracts below give the complete expected end state:",
    ]
    for trace in task.public:
        lines.append(f"{a.describe(task, trace)} => {list(oracle(task, trace))}")
    lines.extend(
        [
            a.guide(lang),
            "The local variable s contains the state before this event. Use only its "
            "fields, scalar literals, arithmetic, comparisons, Boolean logic and the listed helpers. "
            'Return {"expression":"one native expression"} without a statement or explanation.',
        ]
    )
    if previous:
        raw, detail = previous
        lines.extend(
            [
                "The previous expression failed. Use the original unchanged slot.",
                raw,
                "Validation: " + detail[:600],
            ]
        )
    return {
        "model": model,
        "prompt": "\n".join(lines),
        "stream": False,
        "keep_alive": "3m",
        "format": {
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
            "additionalProperties": False,
        },
        "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 200, "seed": 43 if previous else 42},
    }


def unpack(raw):
    pairs = json.loads(raw, object_pairs_hook=list)
    if (
        not isinstance(pairs, list)
        or len(pairs) != 1
        or not isinstance(pairs[0], tuple)
        or pairs[0][0] != "expression"
        or not isinstance(pairs[0][1], str)
    ):
        raise ValueError('Return exactly {"expression":"one native expression"}.')
    return pairs[0][1].strip()


def hidden(adapter):
    start = time.monotonic()
    cases = withheld(adapter.task)
    actual = adapter.observe(cases)
    if len(cases) != len(actual):
        raise ValueError("Missing held-out trace")
    wrong = [
        (case, x, oracle(adapter.task, case))
        for case, x in zip(cases, actual)
        if not a.same(x, oracle(adapter.task, case))
    ]
    score = {
        "total": len(cases),
        "wrong": len(wrong),
        "outcomes_sha256": digest(json.dumps(actual).encode()),
        "first_failure": list(wrong[0]) if wrong else None,
    }
    return score, ms(start)


def run_trial(model, task, lang, adapter, port, capture, existing, *, replay):
    previous = None
    attempts = []
    score = None
    wall_start = time.monotonic()
    replayed_model_time = 0
    for n in (1, 2):
        args = prompt(model, task, lang, previous)
        key = (model, task.name, lang, n)
        if key in existing:
            rec = existing[key]
            if rec["request"] != args:
                raise ValueError(f"Recorded prompt differs at {key}")
            reply = rec["reply"]
            replayed_model_time += rec["model_ms"]
        else:
            if replay:
                raise ValueError(f"Missing archived response at {key}")
            start = time.monotonic()
            data = ollama(port, "generate", args)
            took = ms(start)
            if data.get("done") is not True or any(
                type(data.get(k)) is not int for k in ("prompt_eval_count", "eval_count")
            ):
                raise ValueError("Ollama returned an incomplete response or omitted token counts")
            reply = {k: data[k] for k in ("response", "done_reason", "prompt_eval_count", "eval_count")}
            rec = {
                "kind": "call",
                "model": model,
                "task": task.name,
                "language": lang,
                "attempt": n,
                "request": args,
                "reply": reply,
                "model_ms": took,
            }
            write(capture, rec)  # Persist the original response before compiling or scoring it.
        start = time.monotonic()
        try:
            fragment = unpack(reply["response"])
        except (ValueError, RecursionError) as ex:
            fragment = None
            status, detail = "invalid_expression", str(ex)
        else:
            status, detail = adapter.fill(fragment)
        attempts.append(
            {
                "attempt": n,
                "expression": fragment,
                "validation": status,
                "detail": detail,
                "validation_ms": ms(start),
            }
        )
        if status == "pass":
            break
        previous = reply["response"], detail
    wall = ms(wall_start) + replayed_model_time
    scorer = 0
    if attempts[-1]["validation"] == "pass":
        score, scorer = hidden(adapter)
    passed = score is not None and score["wrong"] == 0
    return {
        "kind": "trial",
        "model": model,
        "task": task.name,
        "language": lang,
        "attempts": attempts,
        "score": score,
        "accepted": passed,
        "first_accepted": passed and len(attempts) == 1,
        "clarifications": 0,
        "workflow_ms": wall,
        "scorer_ms": scorer,
    }


def control(task, lang, adapter):
    if lang == "automatic":
        res = a.command(
            [adapter.binary, "complete", adapter.file, "--hole", a.HOLE, "--limit", "64", "--budget", "10000"]
        )
        if res.returncode not in (0, 1, 3):
            raise ValueError("Native automatic completion failed: " + (res.stderr or res.stdout)[:800])
        report = json.loads(res.stdout or res.stderr)
        # Keep the product's own verified answer; ambiguity is a non-selection.
        selection = (
            report.get("expression")
            if report.get("status") in ("verified", "completed", "complete", "unique")
            else None
        )
        if not selection and report.get("status") in ("verified", "completed", "complete", "unique"):
            selection = report.get("selected")
        if isinstance(selection, dict):
            selection = selection.get("expression", selection.get("replacement"))
        if res.returncode == 0 and not isinstance(selection, str):
            raise ValueError(
                "Automatic success without a recognized selected expression: " + str(report)[:800]
            )
        selected = selection if res.returncode == 0 else None
        if selected and adapter.fill(selected)[0] != "pass":
            raise ValueError("Auto-selected expression did not pass checked native filling")
        score = hidden(adapter)[0] if selected else None
        return {
            "kind": "control",
            "arm": lang,
            "task": task.name,
            "language": "gpp",
            "product": report,
            "selected": selected,
            "score": score,
        }
    tested = []
    selected = None
    for node in islice(a.grammar(task), 64):
        code = a.show(node, lang)
        status, detail = adapter.fill(code)
        tested.append({"expression": code, "validation": status})
        if status == "pass":
            selected = code
            break
    score = hidden(adapter)[0] if selected else None
    return {
        "kind": "control",
        "arm": "shared",
        "task": task.name,
        "language": lang,
        "tested": tested,
        "selected": selected,
        "score": score,
    }


def meta(binary, python):
    paths = ["tasks.py", "protocol.md", "freeze.json", "compiler-capture.json", "adapters.py", "compare.py"]
    return {
        "study": "matched-state-holes-v1",
        "sources": {f: digest((HERE / f).read_bytes()) for f in paths},
        "models": MODELS,
        "compiler_sha256": digest(binary.read_bytes()),
        "host": platform.platform(),
        "python": a.checked([python, "--version"]).strip(),
        "rust": a.checked(["rustc", "-V"]).strip(),
        "mypy": a.checked([python, "-m", "mypy", "--version"]).strip(),
    }


def validate_capture(archived, info):
    if (
        archived["study"] != info["study"]
        or archived["sources"] != info["sources"]
        or archived["models"] != MODELS
    ):
        raise ValueError("Frozen source, protocol or model digests changed")


def run(args):
    preflight = args.preflight
    oldrows = []
    with TemporaryDirectory(prefix="gpp-matched-state-") as tmp:
        work = Path(tmp)
        binary = work / "gpp"
        shutil.copy2(args.gpp, binary)
        info = meta(binary, args.python)
        if args.replay or args.archive.exists():
            archived, oldrows = read(args.archive)
            validate_capture(archived, info)
            if not args.replay and archived["compiler_sha256"] != info["compiler_sha256"]:
                raise ValueError("Build changed during collection")
        calls = {
            (r["model"], r["task"], r["language"], r["attempt"]): r for r in oldrows if r["kind"] == "call"
        }
        trials = {(r["model"], r["task"], r["language"]): r for r in oldrows if r["kind"] == "trial"}
        controls = {(r["arm"], r["task"], r["language"]): r for r in oldrows if r["kind"] == "control"}
        if not (args.replay or preflight):
            installed = {m["name"]: m["digest"] for m in ollama(args.port, "tags")["models"]}
            if any(installed.get(m) != h for m, h in MODELS.items()):
                raise ValueError("Local model digests differ")

        def new_adapter(lang, task):
            return a.Adapter(lang, task, work / (lang + "-" + task.name), binary, args.python, oracle)

        if preflight:
            for t in TASKS:
                for language in a.LANGUAGES:
                    ad = new_adapter(language, t)
                    if (
                        ad.fill(a.expr(language, t.old))[0] != "public_failure"
                        or ad.fill(a.expr(language, t.reference))[0] != "pass"
                    ):
                        raise ValueError(f"Starter or reference preflight failed for {language}/{t.name}")
                    if hidden(ad)[0]["wrong"]:
                        raise ValueError(f"Oracle and native reference disagree for {language}/{t.name}")
            print(
                "All 12 native references passed public and withheld checks; all starters failed visible behavior."
            )
            return
        if not args.replay and not args.archive.exists():
            with args.archive.open("x") as store:
                write(store, info)
        store = None if args.replay else args.archive.open("a", buffering=1)
        try:
            if not args.controls_only:
                for m, t, language in roster():
                    prior = trials.get((m, t.name, language))
                    if prior is not None and not args.replay:
                        continue
                    record = run_trial(
                        m, t, language, new_adapter(language, t), args.port, store, calls, replay=args.replay
                    )
                    if args.replay:
                        if prior is None:
                            raise ValueError("Incomplete trial roster")
                        for x, y in zip(record["attempts"], prior["attempts"], strict=True):
                            x["validation_ms"] = y["validation_ms"]
                        for k in ("workflow_ms", "scorer_ms"):
                            record[k] = prior[k]
                        if not a.same(prior, record):
                            raise ValueError(f"Outcome changed on {m}/{t.name}/{language}")
                    else:
                        write(store, record)
                        print(m, t.name, language, "accepted" if record["accepted"] else "failed", flush=True)
            if not args.models_only:
                for t in TASKS:
                    for language in (*a.LANGUAGES, "automatic"):
                        lang = "gpp" if language == "automatic" else language
                        arm = "automatic" if language == "automatic" else "shared"
                        key = (arm, t.name, lang)
                        if key in controls and not args.replay:
                            continue
                        value = control(t, language, new_adapter(lang, t))
                        if args.replay:
                            if key not in controls or not a.same(value, controls[key]):
                                raise ValueError(f"Control outcome changed for {key}")
                        else:
                            write(store, value)
                            print(arm, t.name, lang, value["selected"], flush=True)
        finally:
            if store:
                store.close()
    if args.replay:
        print("Replayed all requested native assignments and controls against the frozen source.")


def report(path):
    info, rows = read(path)
    calls = [r for r in rows if r["kind"] == "call"]
    trials = [r for r in rows if r["kind"] == "trial"]
    controls = [r for r in rows if r["kind"] == "control"]
    if len(trials) != 24 or len(controls) != 16:
        raise ValueError("Incomplete trial/control roster")
    print("# State-transition maintenance across three languages\n")
    print(
        "Two pinned local models each attempted four previously unseen changes in each language. "
        "Public checks constrained the generated expression. Independent history-based oracles then "
        "tested the full end state on each withheld event sequence.\n"
    )
    print(
        "| Model | Language | First accepted | Final accepted | Calls | Input | Output | Tokens/accept | Model s | Tool/overhead s | Workflow s |"
    )
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for model in MODELS:
        for language in a.LANGUAGES:
            g = [r for r in trials if (r["model"], r["language"]) == (model, language)]
            c = [r for r in calls if (r["model"], r["language"]) == (model, language)]
            inputs = sum(r["reply"]["prompt_eval_count"] for r in c)
            outputs = sum(r["reply"]["eval_count"] for r in c)
            n = sum(r["accepted"] for r in g)
            first = sum(r["first_accepted"] for r in g)
            ratio = f"{(inputs + outputs) / n:,.1f}" if n else "undefined"
            model_ms = sum(r["model_ms"] for r in c)
            workflow = sum(r["workflow_ms"] for r in g)
            print(
                f"| {model} | {language} | {first}/4 | {n}/4 | {len(c)} | {inputs:,} | {outputs:,} | {ratio} | "
                f"{model_ms / 1000:.2f} | {(workflow - model_ms) / 1000:.2f} | {workflow / 1000:.2f} |"
            )
    print("\n| Family | GPT++ | Rust | Typed Python | Shared grammar (GPT++/Rust/Python) | GPT++ automatic |")
    print("|---|---:|---:|---:|---|---|")

    def accepted(control):
        return bool(control["score"] and control["score"]["wrong"] == 0)

    for t in TASKS:
        g = [r for r in trials if r["task"] == t.name]
        by = {r["language"]: r for r in controls if r["task"] == t.name and r["arm"] == "shared"}
        auto = next(r for r in controls if r["task"] == t.name and r["arm"] == "automatic")
        counts = [
            str(sum(r["accepted"] for r in g if r["language"] == language)) + "/2" for language in a.LANGUAGES
        ]
        status = auto["product"]["status"]
        print(
            f"| {t.name} | {' | '.join(counts)} | "
            f"{'/'.join('pass' if accepted(by[language]) else 'fail' for language in a.LANGUAGES)} | "
            f"{'pass' if accepted(auto) else status} |"
        )
    timing = json.loads((HERE / "freeze.json").read_text())
    print(
        f"\nShared task, public-contract and oracle design took {timing['elapsed_seconds']:.3f} seconds of "
        "AI-agent wall time from initial design to freeze. This shared cost was incurred once. "
        "Human labor and language-specific specification-authoring time were unmeasured. There were "
        "zero external clarifications; each automatic retry used only a type error or visible failing "
        "sequence. Model and validation time exclude subsequent withheld scoring. Local typechecking "
        "and compilation tools differ, so these workflow times include their actual adapter costs.\n"
    )
    print(
        "The shared controller, constraints and public information are matched across native languages. "
        "The model-free control removes inference and fixes candidate ordering. The GPT++ automatic "
        "column measures its separate built-in search and ambiguity policy. Four task families and two "
        "models are insufficient to establish a general language advantage. These programs keep their "
        "state in memory; the study does not measure distributed updates or multi-module integration."
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group()
    for name in ("replay", "report", "preflight"):
        mode.add_argument("--" + name, action="store_true")
    sub = p.add_mutually_exclusive_group()
    for name in ("models-only", "controls-only"):
        sub.add_argument("--" + name, action="store_true")
    p.add_argument("--gpp", type=Path, default=ROOT / "target/debug/gpp")
    p.add_argument("--python", type=Path, default=ROOT / "target/empirical-venv/bin/python")
    p.add_argument("--port", type=int, default=11434)
    p.add_argument("archive", type=Path)
    args = p.parse_args()
    if args.report:
        report(args.archive)
    else:
        run(args)
