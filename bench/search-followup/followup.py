"""Collect or replay the independent CodingBat scalar follow-up."""

import argparse
import ast
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import monotonic

import corpus

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "Cargo.toml").is_file())
FIRST = ROOT / "bench/search"
sys.path.append(str(FIRST))
import engine
import native
import study
from portable import search


def fingerprints():
    files = list(HERE / s for s in ("corpus.py","protocol.md","freeze.json","followup.py","portable.py"))
    files.extend(FIRST / s for s in ("engine.py","native.py","study.py"))
    files.extend((ROOT / "bench/stateful/adapters.py", ROOT / "tools/propose.py"))
    return {("local/" + p.name if p.parent == HERE else str(p.relative_to(ROOT))): native.digest(p.read_bytes()) for p in files}


def reference_tree(src):
    operators = {
        ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.FloorDiv: "/", ast.Mod: "%",
        ast.Gt: ">", ast.Lt: "<", ast.GtE: ">=", ast.LtE: "<=", ast.Eq: "==", ast.NotEq: "!=",
        ast.And: "and", ast.Or: "or",
    }
    def convert(n):
        if isinstance(n, ast.Name):
            return n.id
        if isinstance(n, ast.Constant):
            return n.value
        if isinstance(n, ast.BinOp):
            return operators[type(n.op)], convert(n.left), convert(n.right)
        if isinstance(n, ast.Compare):
            return operators[type(n.ops[0])], convert(n.left), convert(n.comparators[0])
        if isinstance(n, ast.BoolOp):
            first, *rest = [convert(v) for v in n.values]
            for child in rest:
                first = operators[type(n.op)], first, child
            return first
        if isinstance(n, ast.IfExp):
            return "if", convert(n.test), convert(n.body), convert(n.orelse)
        if isinstance(n, ast.Call):
            return (n.func.id, *(convert(v) for v in n.args))
        raise ValueError(ast.dump(n))
    return convert(ast.parse(src, mode="eval").body)


def preflight(previous, work):
    rows = []
    for task in corpus.TASKS:
        for lang in native.LANGS:
            ad = native.Program(task, lang, work/lang/task.name, previous)
            starter = study.check(ad, engine.render(reference_tree(task.old), lang), trusted=True)
            reference = study.check(ad, engine.render(reference_tree(task.reference), lang), trusted=True)
            if not reference["accepted"]:
                raise ValueError((task.name,lang,reference))
            rows.append({"task":task.name, "language":lang, "starter_public":starter["public_status"],
                         "starter_correct":starter["accepted"], "reference":reference["score"]})
    return rows


def without_clocks(value):
    if isinstance(value, list):
        return [without_clocks(x) for x in value]
    if isinstance(value, dict):
        return {k:without_clocks(v) for k,v in value.items() if not k.endswith("_ms")}
    return value


def admit(row, raw, archive, replay):
    if replay:
        original = raw[row["kind"],row["key"]]
        if study.stable(without_clocks(original)) != study.stable(without_clocks(row)):
            raise ValueError("Replay diverged: "+row["key"])
    else:
        study.append(archive, row)


def solvers(old, current, raw, directory, archive, replay):
    for task in corpus.TASKS:
        for arm, compiler, options in (("previous", old, []), ("strict", current, []),
                                        ("minimum", current, ["--search","minimum"])):
            key = f"{arm}/{task.name}"
            if not replay and ("solver",key) in raw:
                continue
            backend = native.Program(task, "gpp", directory/arm/task.name, compiler)
            start = monotonic()
            try:
                p = native.run([compiler,"complete",backend.sketch,"--hole","change","--limit","256",
                                "--budget","10000",*options],timeout=30)
                if p.returncode not in (0,1,3):
                    raise RuntimeError(native.rc(p))
                report = json.loads(p.stdout)
            except subprocess.TimeoutExpired:
                report = {"status":"timeout"}
            elapsed = study.millis(start)
            fragment = report.get("selected")
            result = study.check(backend,fragment,trusted=True)
            row = {"kind":"solver","key":key,"report":report,"expression":fragment,"search_ms":elapsed,**result}
            admit(row,raw,archive,replay)

        key = "shared/"+task.name
        if not replay and ("shared",key) in raw:
            continue
        inputs,_ = corpus.cases(task)
        answers = tuple(corpus.expected(task,args) for args in inputs)
        start = monotonic()
        selections, stats = search(task.args, task.result, inputs, answers, start+30)
        elapsed = study.millis(start)
        compared, cache = {}, {}
        for policy, node in selections.items():
            compared[policy] = {}
            for lang in native.LANGS:
                fragment = engine.render(node,lang) if node is not None else None
                if (lang,fragment) not in cache:
                    ad = native.Program(task,lang,directory/lang/task.name,old)
                    cache[lang,fragment] = {"expression":fragment, **study.check(ad,fragment,trusted=True)}
                compared[policy][lang] = cache[lang,fragment]
        row = {"kind":"shared","key":key,"stats":stats,"search_ms":elapsed,"selections":compared}
        admit(row,raw,archive,replay)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("phase",choices=("models","solvers","preflight","replay"))
    p.add_argument("archive",type=Path)
    p.add_argument("--old",required=True,type=Path)
    p.add_argument("--new",type=Path)
    args = p.parse_args()
    replay = args.phase == "replay"
    with TemporaryDirectory(prefix="gpp-cost-followup-") as temporary:
        work = Path(temporary)
        old = work/"old-gpp"
        shutil.copy2(args.old, old)
        current = work/"new-gpp"
        if args.phase in ("solvers","replay"):
            if not args.new:
                p.error("--new is required")
            shutil.copy2(args.new,current)
        if args.phase == "preflight":
            if args.archive.exists():
                raise ValueError("Choose a new preflight output path")
            args.archive.write_text(json.dumps(preflight(old,work),indent=2)+"\n")
            return
        rows = study.load(args.archive)
        if not rows:
            if replay:
                raise ValueError("Missing archive")
            study.append(args.archive,{"kind":"manifest","time_utc":study.stamp(),"files":fingerprints(),
                "old_sha256":native.digest(old.read_bytes()),"models":study.MODELS,"host":platform.platform(),
                "python":native.run([native.PYTHON,"-V"]).stdout.strip(),"rust":native.run(["rustc","-V"]).stdout.strip(),
                "mypy":native.run([native.PYTHON,"-m","mypy","--version"]).stdout.strip()})
        else:
            if rows[0]["files"] != fingerprints():
                raise ValueError("Frozen source differs")
            if not replay and rows[0]["old_sha256"] != native.digest(old.read_bytes()):
                raise ValueError("Previous binary changed")
        raw = {(r["kind"], r["key"]):r for r in rows if "key" in r}
        if len(raw) != len([r for r in rows if "key" in r]):
            raise ValueError("Duplicate measurement key")
        if args.phase in ("models","replay"):
            study.model_runs(old,raw,work,args.archive,replay)
        if args.phase in ("solvers","replay"):
            captured = [r for r in rows if r["kind"] == "compiler"]
            if not captured:
                if replay:
                    raise ValueError("Missing compiler capture")
                study.append(args.archive,{"kind":"compiler","new_sha256":native.digest(current.read_bytes()),"time_utc":study.stamp()})
            elif not replay and captured[0]["new_sha256"] != native.digest(current.read_bytes()):
                raise ValueError("Minimum-mode binary changed")
            solvers(old,current,raw,work,args.archive,replay)
    if replay:
        print("Verified all original prompts, public outcomes, selected fragments, proposal counters and hidden score digests.")


if __name__ == "__main__":
    main()
