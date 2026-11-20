"""Generate the final confirmation tables without a model or compiler."""

import argparse
from collections import Counter
from pathlib import Path

from confirm import CAPS, corpus, native, study


def outcome(row):
    if row["accepted"]:
        return "correct"
    return "wrong" if row["score"] else "—"


def main(path):
    rows = study.load(path)
    sizes = Counter(r["kind"] for r in rows)
    if sizes != {"manifest":1,"compiler":1,"call":66,"trial":66,"native":44,"portable":33}:
        raise ValueError(f"Unexpected roster: {sizes}")
    by = {(r["kind"],r.get("key")):r for r in rows}
    if len(by) != len(rows):
        raise ValueError("Duplicate keys")
    tasks = corpus.TASKS

    def built(arm, t):
        return by["native",f"{arm}/{t.name}"]

    def shared(cap, t):
        return by["portable",f"{cap}/{t.name}"]

    def choices(cap, policy, lang):
        return [shared(cap,t)["selections"][policy][lang] for t in tasks]

    print("# Final confirmation on eleven external scalar exercises\n")
    print("Two contiguous eligible slices from CodingBat contributed 11 directly specified rules, 264 public examples and 2,342 independently checked withheld inputs. These tasks were frozen before inspecting the piecewise implementation. A correct publication passed every test in its native backend. The unit counted below is a whole exercise. Several exercises share mathematical structure. [Frozen selection and qualification rule](protocol.md) · [Public source exercises](sources.md)\n")
    print("| Automatic solver | Correct / 11 | Published | Published wrong | Ambiguous | Incomplete | Search seconds |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    arms = ("previous","strict","minimum","piecewise")
    for arm in arms:
        group = [built(arm,t) for t in tasks]
        ok = sum(r["accepted"] for r in group)
        pub = sum(r["expression"] is not None for r in group)
        states = Counter(r["report"]["status"] for r in group)
        print(f"| {arm} | {ok} | {pub} | {pub-ok} | {states['ambiguous']} | {states['incomplete']} | {sum(r['search_ms'] for r in group)/1000:.3f} |")
    print("\n| Portable search | Selector | Correct GPT++ / 11 | Typed Python | Rust | Published | Published wrong | Search seconds |")
    print("|---|---|---:|---:|---:|---:|---:|---:|")
    for cap in CAPS:
        for policy in ("first","conservative","minimum"):
            scores = [sum(r["accepted"] for r in choices(cap,policy,lang)) for lang in ("gpp","python","rust")]
            published = sum(r["expression"] is not None for r in choices(cap,policy,"gpp"))
            print(f"| {cap} | {policy} | "+" | ".join(map(str,scores))+f" | {published} | {published-scores[0]} | {sum(shared(cap,t)['search_ms'] for t in tasks)/1000:.3f} |")
    print("\nThe compact portable beam and both larger cost-layered beams had the same cap of 256 fully submitted roots and the same 30-second deadline. The two cost-layered controls allow 152,192 and 302,192 intermediate operations. The three policies within each size share the same candidate search and elapsed time. Each selected result was separately rendered, statically checked and executed in its actual language. Public validation times are archived per backend.\n")
    print("| Native task | Previous | Strict hybrid | Minimum cost | Piecewise | Withheld |")
    print("|---|---|---|---|---|---:|")
    for t in tasks:
        cells = []
        for arm in arms:
            r=built(arm,t)
            cells.append(outcome(r) if r["expression"] is not None else r["report"]["status"])
        print(f"| {t.name} | "+" | ".join(cells)+f" | {len(corpus.cases(t)[1])} |")
    print("\n| Task | Compact first / consensus / minimum | Expanded first / consensus / minimum | Larger first / consensus / minimum |")
    print("|---|---|---|---|")
    for t in tasks:
        cells = []
        for cap in CAPS:
            row=shared(cap,t)
            selections=[]
            for policy in ("first","conservative","minimum"):
                results=[outcome(row["selections"][policy][l]) for l in native.LANGS]
                selections.append(results[0] if len(set(results))==1 else ", ".join(results))
            cells.append(" / ".join(selections))
        print(f"| {t.name} | "+" | ".join(cells)+" |")
    print("\n## Published piecewise expressions\n")
    print("| Exercise | Exact selected expression | Wrong withheld inputs | First disagreement |")
    print("|---|---|---:|---|")
    for task in tasks:
        row=built("piecewise",task)
        if row["score"] is None:
            continue
        score=row["score"]
        failure=score["first_error"]
        example="—" if failure is None else f"{failure[1][1]} expected {failure[2]}, returned {failure[3]}"
        # Markdown tables require pipe characters to be escaped even inside code spans.
        code=row["expression"].replace("|",chr(92)+"|")
        print(f"| {task.name} | `{code}` | {score['direct_wrong']} | {example} |")
    print("\n## Paired primary endpoint\n")
    print("| Piecewise compared with | Wins | Losses | Both correct | Both failed |")
    print("|---|---:|---:|---:|---:|")
    target = [built("piecewise",t)["accepted"] for t in tasks]
    other = [(arm,[built(arm,t)["accepted"] for t in tasks]) for arm in arms[:-1]]
    other += [(cap+" "+policy,[r["accepted"] for r in choices(cap,policy,"gpp")]) for cap in CAPS for policy in ("first","conservative","minimum")]
    for name,pair in other:
        tally=Counter(zip(target,pair))
        print(f"| {name} | {tally[True,False]} | {tally[False,True]} | {tally[True,True]} | {tally[False,False]} |")
    previous=sum(built("minimum",t)["accepted"] for t in tasks)
    primary_portable=sum(r["accepted"] for r in choices("larger","minimum","gpp"))
    positive=sum(target)>max(previous,primary_portable)
    print(f"\nThe piecewise selector solved **{sum(target)}/11**, the preceding native minimum-cost mode solved **{previous}/11** and the larger portable minimum-cost control solved **{primary_portable}/11**. The preregistered condition required greater acceptance than both earlier controls. The experiment **{'met' if positive else 'did not meet'}** that condition. These counts concern eleven bounded exercises.\n")
    print("## Fresh one-call model generation\n")
    print("| Model | Language | Correct / 11 | Passed public | Calls | Input tokens | Output tokens | Model s | Public validation s |")
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for model in study.MODELS:
        for lang in native.LANGS:
            trials=[by["trial",f"{model}/{t.name}/{lang}"] for t in tasks]
            calls=[by["call",f"{model}/{t.name}/{lang}"] for t in tasks]
            print(f"| {model} | {lang} | {sum(x['accepted'] for x in trials)} | {sum(x['score'] is not None for x in trials)} | {len(calls)} | "
                  f"{sum(x['reply']['prompt_eval_count'] for x in calls):,} | {sum(x['reply']['eval_count'] for x in calls):,} | "
                  f"{sum(x['model_ms'] for x in calls)/1000:.2f} | {sum(x['public_ms'] for x in trials)/1000:.2f} |")
    print("\n| Task | Qwen GPT++ | Qwen Python | Qwen Rust | StarCoder2 GPT++ | StarCoder2 Python | StarCoder2 Rust |")
    print("|---|---|---|---|---|---|---|")
    for t in tasks:
        r=[outcome(by["trial",f"{m}/{t.name}/{l}"]) for m in study.MODELS for l in ("gpp","python","rust")]
        print(f"| {t.name} | "+" | ".join(r)+" |")
    print("\nA dash means the public or type gate withheld publication. “Wrong” means a published expression failed at least one withheld input. There were zero retries and zero external clarifications. English instructions were available to the models. Automatic solvers received the same labeled examples in the task module. The public external exercises may have appeared in model training.\n")
    print("## Actual intermediate search work\n")
    print("| Native mode | Root candidates tested | Guidance contract runs | Guidance vectors | Minimum-cost vectors | Numeric hypotheses | Additional piecewise counters |")
    print("|---|---:|---:|---:|---:|---:|---|")
    for arm in arms:
        group=[built(arm,t)["report"] for t in tasks]
        def total(part,key):
            return sum(r.get(part,{}).get(key,0) or 0 for r in group)
        extras=Counter()
        for row in group:
            for part in ("selection","piecewise"):
                for key,val in row.get(part,{}).items():
                    if type(val) is int and key not in ("cost","value_vectors","numeric_hypotheses","longer_passing"):
                        extras[part+"."+key]+=val
        extra=", ".join(f"{k}={v:,}" for k,v in sorted(extras.items())) or "—"
        print(f"| {arm} | {sum(r.get('tested',0) for r in group):,} | {total('guidance','contract_runs'):,} | {total('guidance','value_vectors'):,} | "
              f"{total('selection','value_vectors'):,} | {total('selection','numeric_hypotheses'):,} | {extra} |")
    print("\n| Portable mode | Intermediate vector evaluations | Branch comparisons | Root checks | Wall timeouts |")
    print("|---|---:|---:|---:|---:|")
    for cap in CAPS:
        stats = [shared(cap,t)["stats"] for t in tasks]
        print(f"| {cap} | {sum(x.get('vectors',x.get('vector_evaluations',0)) for x in stats):,} | "
              f"{sum(x['partition_tests'] for x in stats):,} | {sum(x['root_checks'] for x in stats):,} | {sum(x['time_limit_hit'] for x in stats)} |")
    print("\nCounters refer to different internal operations and are not instruction or CPU budgets. Native search timing includes the compiler's internal validation. Portable search timings cover candidate search, with separate public native validation in the archive. All wall-time observations are host- and load-dependent. Full per-task proposals and diagnostics are in the [raw archive](results.jsonl). [Offline reproduction](README.md)")


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive",type=Path)
    main(parser.parse_args().archive)
