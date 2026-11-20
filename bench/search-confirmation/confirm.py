"""Collect and replay the final, externally specified piecewise confirmation block."""

import argparse
from contextlib import contextmanager
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
SECOND = ROOT / "bench/search-followup"
sys.path.append(str(SECOND))
import followup
import expanded
from followup import engine, native, study
from portable import search as small_search

FORMS = ("models","native","portable","preflight","replay")
CAPS = {
    "compact": None,
    "expanded": (152192, (2000,12000,18000,42000,53000,78000,87000,110000,126000,140000)),
    "larger": (302192, (4000,24000,36000,84000,106000,156000,174000,220000,252000,280000)),
}


def hashes():
    local = {p:native.digest((HERE/p).read_bytes()) for p in ("corpus.py","confirm.py","freeze.json","protocol.md")}
    files = [ROOT/"bench/search"/name for name in ("native.py","engine.py","study.py")]
    files += [SECOND/name for name in ("followup.py","portable.py","expanded.py")]
    files += [ROOT/"bench/stateful/adapters.py",ROOT/"tools/propose.py"]
    return dict(local, **{str(p.relative_to(ROOT)):native.digest(p.read_bytes()) for p in files})


@contextmanager
def set_work_budget(cap, layers):
    previous = expanded.CAP, expanded.CUMULATIVE
    expanded.CAP, expanded.CUMULATIVE = cap, layers
    try:
        yield
    finally:
        expanded.CAP, expanded.CUMULATIVE = previous


def portable_work(t, kind, old, work):
    if kind == "compact":
        rows,_ = corpus.cases(t)
        labels = tuple(corpus.expected(t,r) for r in rows)
        start = monotonic()
        nodes, stats = small_search(t.args,t.result,rows,labels,start+30)
        elapsed = study.millis(start)
    else:
        with set_work_budget(*CAPS[kind]):
            nodes,stats,elapsed = expanded.search(t)
    results = {}
    cache = {}
    for policy,node in nodes.items():
        results[policy] = {}
        for lang in native.LANGS:
            expression = engine.render(node,lang) if node is not None else None
            if (lang,expression) not in cache:
                backend = native.Program(t,lang,work/lang/t.name,old)
                cache[lang,expression] = {"expression":expression, **study.check(backend,expression,trusted=True)}
            results[policy][lang] = cache[lang,expression]
    return {"kind":"portable","key":f"{kind}/{t.name}","stats":stats,"search_ms":elapsed,"selections":results}


def solver(t, arm, binary, work):
    options = [] if arm in ("previous","strict") else ["--search",arm]
    ad = native.Program(t,"gpp",work/arm/t.name,binary)
    start = monotonic()
    try:
        p = native.run([binary,"complete",ad.sketch,"--hole","change","--limit","256",
                        "--budget","10000",*options],timeout=30)
        if p.returncode not in (0,1,3):
            raise RuntimeError(native.rc(p))
        report = json.loads(p.stdout)
    except subprocess.TimeoutExpired:
        report = {"status":"timeout"}
    elapsed = study.millis(start)
    expression = report.get("selected")
    return {"kind":"native","key":f"{arm}/{t.name}","expression":expression,"report":report,
            "search_ms":elapsed, **study.check(ad,expression,trusted=True)}


def admit(raw,archive,row,replay):
    key = row["kind"],row["key"]
    if replay and row["kind"]=="portable" and raw[key]["stats"].get("time_limit_hit"):
        if not row["stats"]["time_limit_hit"]:
            raise ValueError("A captured timeout finished inside the wall budget on replay: "+row["key"])
        # A wall timeout can interrupt different intermediate cells across hosts. Its scored outcome must still match.
        if study.stable(followup.without_clocks(row["selections"])) != study.stable(followup.without_clocks(raw[key]["selections"])):
            raise ValueError("Timeout publication changed: "+row["key"])
        return
    followup.admit(row,raw,archive,replay)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("phase",choices=FORMS)
    p.add_argument("archive",type=Path)
    p.add_argument("--old",required=True,type=Path)
    p.add_argument("--prior",type=Path)
    p.add_argument("--new",type=Path)
    args=p.parse_args()
    replay=args.phase=="replay"
    with TemporaryDirectory(prefix="gpp-final-confirm-") as tmp:
        work=Path(tmp)
        old=work/"previous-binary"; shutil.copy2(args.old,old)
        prior,current=work/"minimum-binary",work/"piecewise-binary"
        if args.phase in ("native","replay"):
            if not args.new or not args.prior:
                p.error("--prior and --new are required for native/replay")
            shutil.copy2(args.prior,prior); shutil.copy2(args.new,current)
        if args.phase=="preflight":
            if args.archive.exists(): raise ValueError("Choose a new preflight path")
            args.archive.write_text(json.dumps(followup.preflight(old,work),indent=2)+"\n")
            return
        original=study.load(args.archive)
        if original:
            if original[0]["files"]!=hashes() or (not replay and original[0]["old"]!=native.digest(old.read_bytes())):
                raise ValueError("Pinned source or original compiler changed")
        elif replay:
            raise ValueError("Missing archive")
        else:
            study.append(args.archive,{"kind":"manifest","files":hashes(),"old":native.digest(old.read_bytes()),
                "time_utc":study.stamp(),"models":study.MODELS,"host":platform.platform(),
                "python":native.run([native.PYTHON,"-V"]).stdout.strip(),"rust":native.run(["rustc","-V"]).stdout.strip(),
                "mypy":native.run([native.PYTHON,"-m","mypy","--version"]).stdout.strip()})
        raw={(r["kind"],r["key"]):r for r in original if "key" in r}
        if len(raw)!=sum("key" in r for r in original): raise ValueError("Duplicate measurement key")
        if args.phase in ("models","replay"):
            # The complete canonical renderer adds <= and != in these tasks' prior expressions.
            engine.parse_py=followup.reference_tree
            study.model_runs(old,raw,work,args.archive,replay)
        if args.phase in ("native","replay"):
            current_hashes={k:native.digest(p.read_bytes()) for k,p in (("prior",prior),("piecewise",current))}
            recorded=next((r["binaries"] for r in original if r["kind"]=="compiler"),None)
            if recorded is None:
                if replay: raise ValueError("Missing compiler receipt")
                study.append(args.archive,{"kind":"compiler","binaries":current_hashes,"time_utc":study.stamp()})
            elif not replay and recorded!=current_hashes:
                raise ValueError("Captured native binaries changed")
            for t in corpus.TASKS:
                for arm,binary in (("previous",old),("strict",prior),("minimum",prior),("piecewise",current)):
                    key="native",f"{arm}/{t.name}"
                    if replay or key not in raw:
                        admit(raw,args.archive,solver(t,arm,binary,work),replay)
        if args.phase in ("portable","replay"):
            for t in corpus.TASKS:
                for cap in CAPS:
                    key="portable",f"{cap}/{t.name}"
                    if replay or key not in raw:
                        admit(raw,args.archive,portable_work(t,cap,old,work),replay)
                print("Portable controls finished",t.name,flush=True)
    if replay:
        print("All frozen confirmation model prompts, solver selections and independent held-out outcomes matched.")


if __name__=="__main__":
    main()
