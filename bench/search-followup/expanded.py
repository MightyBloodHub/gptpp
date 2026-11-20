"""Larger pre-budgeted portable comparator for the independent minimum-cost study."""

import argparse
from collections import defaultdict
from dataclasses import dataclass
from itertools import product
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from time import monotonic

import corpus
from followup import HERE, admit, fingerprints, native, study
from engine import BOOL, COMMUTE, INT, OPS_B, OPS_I, operation, probes, render

CAP = 152192
CUMULATIVE = (2000,12000,18000,42000,53000,78000,87000,110000,126000,140000)


@dataclass
class Term:
    node: object
    values: tuple
    cost: int


def search(task):
    started = monotonic()
    deadline = started + 30
    public,_ = corpus.cases(task)
    ans = tuple(corpus.expected(task, r) for r in public)
    extra = probes(task.args)
    inputs = public + extra
    n = len(public)
    seen = {INT:{}, BOOL:{}}
    layers = defaultdict(dict)
    fits = {}
    first = None
    stats = {"vectors":0, "partition_tests":0, "root_checks":0, "probe_rows":len(extra)}

    def register(typ, term):
        nonlocal first
        old = seen[typ].get(term.values)
        if old and old.cost <= term.cost:
            return
        seen[typ][term.values] = term
        layers[typ,term.cost][term.values] = term
        if typ != task.result or stats["root_checks"] >= 256 or term.values[:n] != ans:
            return
        stats["root_checks"] += 1
        if first is None:
            first = term
        fits[term.values[n:]] = term

    def emit(typ, op, children):
        stats["vectors"] += 1
        register(typ,Term((op,*(v.node for v in children)),
                          tuple(operation(op,xs) for xs in zip(*(c.values for c in children))),
                          1+sum(v.cost for v in children)))

    for i,(name,typ) in enumerate(task.args):
        register(typ, Term(name,tuple(row[i] for row in inputs),1))
    integers = {0,1,2,-1}
    integers.update(v for row in public for v in row if type(v) is int)
    integers.update(v for v in ans if type(v) is int)
    for v in sorted(integers,key=lambda x:(abs(x),x))[:32]:
        register(INT,Term(v,(v,)*len(inputs),1))
    for v in (False,True):
        register(BOOL,Term(v,(v,)*len(inputs),1))

    def quality(term):
        hits = sum(type(x) is type(y) and x == y for x,y in zip(term.values,ans))
        distance = sum(10000 if x is None else min(10000,abs(int(x)-int(y))) for x,y in zip(term.values,ans))
        return -hits,distance

    beams = {}
    def beam(typ, size):
        key = typ,size
        if key not in beams:
            values = list(layers[key].values())
            # Combine admission order, public agreement, numerical proximity, and syntactic simplicity.
            scored = [(quality(item),item) for item in values]
            best = [item for _, item in sorted(scored,key=lambda p:p[0])[:36]]
            nearby = [item for _, item in sorted(scored,key=lambda p:(p[0][1],p[0][0]))[:20]]
            simplest = sorted(values,key=lambda item:(len(str(item.node)),str(item.node)))[:18]
            chosen = {item.values:item for item in best+nearby+simplest+values[:36]}
            beams[key] = list(chosen.values())
        return beams[key]

    def pairs(xs,ys,commutative):
        for x in xs:
            for y in ys:
                if commutative and str(y.node)<str(x.node) and xs is ys:
                    continue
                yield x,y

    families = [(INT,INT,OPS_I),(INT,BOOL,OPS_B),(BOOL,BOOL,("and","or","==","!="))]
    levels=[]
    for size, ceiling in enumerate(CUMULATIVE, start=2):
        if monotonic() > deadline:
            break
        jobs = []
        for node in beam(BOOL,size-1):
            if stats["vectors"] >= ceiling:
                break
            emit(BOOL,"not",(node,))
            emit(INT,"int",(node,))
        for left_size in range(1,size-1):
            right_size = size-1-left_size
            for arg_type,out_type,ops in families:
                xs,ys = beam(arg_type,left_size),beam(arg_type,right_size)
                if not xs or not ys:
                    continue
                for op in ops:
                    if op in COMMUTE and left_size>right_size:
                        continue
                    jobs.append((out_type,op,pairs(xs,ys,op in COMMUTE)))
        while jobs and stats["vectors"]<ceiling and monotonic()<deadline:
            next_jobs=[]
            for typ,op,stream in jobs:
                if stats["vectors"] >= ceiling:
                    break
                kids=next(stream,None)
                if kids is not None:
                    emit(typ,op,kids)
                    next_jobs.append((typ,op,stream))
            jobs=next_jobs
        levels.append(stats["vectors"])
    # Exact public branch partitions. Charge each tested signature as one vector operation.
    def all_terms(typ):
        values=list(seen[typ].values())
        return sorted(values,key=lambda term:(quality(term),term.cost))
    predicates, results=all_terms(BOOL)[:160], all_terms(task.result)[:300]
    def available():
        return stats["vectors"]+stats["partition_tests"]<CAP and monotonic()<deadline
    for cond in predicates:
        if not available():
            break
        flags=cond.values[:n]
        if None in flags or len(set(flags))<2:
            continue
        yes,no=[],[]
        for term in results:
            if not available():
                break
            stats["partition_tests"] += 1
            if all(x==y for choose,x,y in zip(flags,term.values,ans) if choose):
                yes.append(term)
            if all(x==y for choose,x,y in zip(flags,term.values,ans) if not choose):
                no.append(term)
        for a,b in product(yes[:3],no[:3]):
            if not available():
                break
            emit(task.result,"if",(cond,a,b))

    stats["distinct_vectors"]=sum(map(len,seen.values()))
    stats["work"]=stats["vectors"]+stats["partition_tests"]
    stats["layers_cumulative"]=levels
    stats["behaviors"]=len(fits)
    min_cost=min((p.cost for p in fits.values()),default=None)
    cheapest=[p for p in fits.values() if p.cost==min_cost]
    stats["minimum_cost"]=min_cost
    stats["shortest_behaviors"]=len(cheapest)
    stats["time_limit_hit"]=monotonic()>deadline
    selected={"first":first, "conservative":first if len(fits)==1 else None,
              "minimum":cheapest[0] if len(cheapest)==1 else None}
    result={k:v.node if v is not None and not stats["time_limit_hit"] else None for k,v in selected.items()}
    return result,stats,study.millis(started)


def compare(task,previous,work):
    nodes,stats,elapsed=search(task)
    selections,cache={},{}
    for policy,node in nodes.items():
        selections[policy]={}
        for lang in native.LANGS:
            expression=render(node,lang) if node is not None else None
            if (lang,expression) not in cache:
                adapter=native.Program(task,lang,work/lang/task.name,previous)
                cache[lang,expression]={"expression":expression,**study.check(adapter,expression,trusted=True)}
            selections[policy][lang]=cache[lang,expression]
    return {"kind":"expanded","key":task.name,"search_ms":elapsed,"stats":stats,"selections":selections}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("mode",choices=("collect","replay","report"))
    p.add_argument("archive",type=Path)
    p.add_argument("--old",type=Path)
    args=p.parse_args()
    if args.mode=="report":
        describe(args.archive)
        return
    if not args.old:
        p.error("--old is required for collection and replay")
    original=study.load(args.archive)
    files=fingerprints()
    files.update({s:native.digest((HERE/s).read_bytes()) for s in ("expanded.py","expanded-protocol.md","expanded-freeze.json")})
    replay=args.mode=="replay"
    if not original:
        if replay: raise ValueError("Missing capture")
        study.append(args.archive,{"kind":"manifest","files":files,"time_utc":study.stamp(),"old_sha256":native.digest(args.old.read_bytes())})
    elif original[0]["files"]!=files or (not replay and original[0]["old_sha256"]!=native.digest(args.old.read_bytes())):
        raise ValueError("Captured source or compiler changed")
    saved={(r["kind"],r["key"]):r for r in original if r["kind"]=="expanded"}
    with TemporaryDirectory(prefix="gpp-expanded-search-") as tmp:
        work=Path(tmp)
        previous=work/"previous-gpp"
        shutil.copy2(args.old,previous)
        for t in corpus.TASKS:
            if replay or ("expanded",t.name) not in saved:
                row=compare(t,previous,work)
                admit(row,saved,args.archive,replay)
                print("Replayed" if replay else "Scored", t.name,flush=True)
    if replay:
        print("All expanded native selections and complete held-out outcome digests matched.")


def describe(path):
    rows={r["key"]:r for r in study.load(path) if r["kind"]=="expanded"}
    if set(rows)!={t.name for t in corpus.TASKS}:
        raise ValueError("Incomplete expanded roster")
    print("# Portable search with a 152,192-operation allowance\n")
    print("This supplemental control was frozen before the new native solver was scored. One portable candidate search per task feeds three publication policies. The actual shared expressions were rendered, type-checked and independently scored in GPT++, typed Python and Rust.\n")
    print("| Policy | Correct / 12 in GPT++ | Typed Python | Rust | Published | Published wrong |")
    print("|---|---:|---:|---:|---:|---:|")
    for policy in ("first","conservative","minimum"):
        scores=[sum(rec["selections"][policy][lang]["accepted"] for rec in rows.values()) for lang in ("gpp","python","rust")]
        pub=sum(rec["selections"][policy]["gpp"]["expression"] is not None for rec in rows.values())
        print(f"| {policy} | "+" | ".join(map(str,scores))+f" | {pub} | {pub-scores[0]} |")
    print("\n| Task | First | Consensus | Minimum | Roots | Minimum cost | Distinct minimum behaviors | Intermediate work | Search s |")
    print("|---|---|---|---|---:|---:|---:|---:|---:|")
    for t in corpus.TASKS:
        r=rows[t.name]; stats=r["stats"]; decisions=[]
        for policy in ("first","conservative","minimum"):
            result=r["selections"][policy]["gpp"]
            decisions.append("correct" if result["accepted"] else "wrong" if result["score"] else "—")
        print(f"| {t.name} | "+" | ".join(decisions)+f" | {stats['root_checks']} | {stats['minimum_cost']} | {stats['shortest_behaviors']} | {stats['work']:,} | {r['search_ms']/1000:.3f} |")
    print(f"\nAcross all twelve tasks, this search used {sum(r['stats']['work'] for r in rows.values()):,} intermediate operations and {sum(r['search_ms'] for r in rows.values())/1000:.3f} seconds. There were {sum(r['stats']['time_limit_hit'] for r in rows.values())} wall-time expirations. These are algorithm-specific vector and partition operations. Matching ceilings does not give the algorithms identical grammars, runtimes or probes. [Secondary protocol](expanded-protocol.md) · [Native and smaller-control results](results.md) · [Raw archive](expanded.jsonl)")


if __name__=="__main__":
    main()
