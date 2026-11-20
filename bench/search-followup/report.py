"""Build the follow-up report from its complete trial roster."""

import argparse
from collections import Counter
from pathlib import Path
import sys

import corpus

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / "Cargo.toml").is_file())
sys.path.append(str(ROOT / "bench/search"))
import native
import study


def report(path):
    rows = study.load(path)
    expected = {"manifest":1,"compiler":1,"call":72,"trial":72,"solver":36,"shared":12}
    if Counter(r["kind"] for r in rows) != expected:
        raise ValueError("Incomplete trial roster")
    index = {(r["kind"], r.get("key")):r for r in rows}
    if len(index) != len(rows):
        raise ValueError("Duplicate trial")
    tasks = corpus.TASKS

    def compiler(arm, task):
        return index["solver",f"{arm}/{task.name}"]

    def shared(task):
        return index["shared","shared/"+task.name]

    def portable(arm, task, lang="gpp"):
        return shared(task)["selections"][arm][lang]

    def label(solved):
        return "correct" if solved["accepted"] else "wrong" if solved["score"] else "—"

    print("# Minimum-cost selection on twelve externally specified exercises\n")
    print("The primary outcome is a native expression that the solver actually published and that passed all withheld inputs. Twelve CodingBat exercises contribute 288 public cases and 22,675 independently scored withheld inputs. The two preceding internal corpora did not include these exercises. Every starter failed its public checks. All 36 native reference implementations passed. One published closeFar example lies outside the finite scoring grid and remains an additional public check. [Task selection and budgets](protocol.md) · [External problem sources](sources.md)\n")
    print("| Selector | Correct / 12 | Published | Published wrong | Ambiguous | Search seconds |")
    print("|---|---:|---:|---:|---:|---:|")
    native_arms = [("previous","Previous GPT++"),("strict","Default GPT++"),("minimum","Minimum-cost GPT++")]
    portable_arms = [("first","Portable first pass"),("conservative","Portable consensus"),("minimum","Portable minimum cost")]
    def table_row(name, entries, ambiguity, time):
        n = sum(e["accepted"] for e in entries)
        published = sum(e["expression"] is not None for e in entries)
        print(f"| {name} | {n} | {published} | {published-n} | {ambiguity} | {time/1000:.3f} |")
    for arm, name in native_arms:
        entries = [compiler(arm,t) for t in tasks]
        table_row(name,entries,sum(e["report"]["status"]=="ambiguous" for e in entries),sum(e["search_ms"] for e in entries))
    for arm, name in portable_arms:
        entries = [portable(arm,t) for t in tasks]
        for t in tasks:
            for lang in native.LANGS:
                if portable(arm,t,lang)["accepted"] != portable(arm,t)["accepted"]:
                    raise ValueError("Split native outcome: "+t.name)
        ambiguity = "n/a" if arm=="first" else sum(shared(t)["stats"]["behaviors" if arm=="conservative" else "shortest_behaviors"]>1 for t in tasks)
        table_row(name,entries,ambiguity,sum(shared(t)["search_ms"] for t in tasks))
    print("\nEach portable row reports one common candidate search. The same candidates were rendered and run in GPT++, typed Python and Rust, yielding identical acceptance in all three. The portable policies chose among at most 256 public-fitting roots. The built-in compiler checked at most 256 submitted roots; each system also performed additional intermediate evaluations. Search timings are one host observation and exclude independent withheld scoring. The portable row times also exclude final native validation, which is recorded by backend in the archive.\n")
    print("| Task | Previous | Default | Minimum cost | Portable first | Portable consensus | Portable minimum | Withheld |")
    print("|---|---|---|---|---|---|---|---:|")
    for t in tasks:
        cells = []
        for arm,_ in native_arms:
            row = compiler(arm,t)
            cells.append(label(row) if row["expression"] is not None else row["report"]["status"])
        cells.extend(label(portable(arm,t)) for arm,_ in portable_arms)
        print(f"| {t.name} | "+" | ".join(cells)+f" | {len(corpus.cases(t)[1]):,} |")
    print("\n## Paired decisions\n")
    print("| Minimum-cost GPT++ compared with | Wins | Losses | Both correct | Both failed |")
    print("|---|---:|---:|---:|---:|")
    target = [compiler("minimum",t)["accepted"] for t in tasks]
    for title,other in [(name,[compiler(arm,t)["accepted"] for t in tasks]) for arm,name in native_arms[:2]] + [
            (name,[portable(arm,t)["accepted"] for t in tasks]) for arm,name in portable_arms]:
        values = Counter(zip(target,other))
        print(f"| {title} | {values[True,False]} | {values[False,True]} | {values[True,True]} | {values[False,False]} |")
    qualifies = sum(target) > max(sum(compiler("strict",t)["accepted"] for t in tasks), sum(portable("minimum",t)["accepted"] for t in tasks))
    if qualifies:
        print("\nMinimum-cost GPT++ met the preregistered criterion of higher independent acceptance than both its default policy and portable minimum-cost search on this block.")
    else:
        print("\nMinimum-cost GPT++ did not meet the preregistered criterion of higher independent acceptance than both its default policy and portable minimum-cost search on this block.")
    print("\nA cheaper public fit can be wrong on held-out values. A solver can also ask a question about a disagreement outside a task’s measured domain. Cost and ambiguity describe the sampled search space; they do not prove behavioral correctness.\n")
    print("## Fresh local model generation\n")
    print("| Model | Language | Correct / 12 | Passed public | Calls | Input tokens | Output tokens | Inference s | Public validation s |")
    print("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for model in study.MODELS:
        for lang in native.LANGS:
            keys = [f"{model}/{t.name}/{lang}" for t in tasks]
            calls = [index["call",k] for k in keys]
            trials = [index["trial",k] for k in keys]
            print(f"| {model} | {lang} | {sum(r['accepted'] for r in trials)} | {sum(r['public_status']=='pass' for r in trials)} | {len(calls)} | "
                  f"{sum(r['reply']['prompt_eval_count'] for r in calls):,} | {sum(r['reply']['eval_count'] for r in calls):,} | "
                  f"{sum(r['model_ms'] for r in calls)/1000:.2f} | {sum(r['public_ms'] for r in trials)/1000:.2f} |")
    print("\nEach task and language received one call per model. All 72 attempts count, with zero retries and zero external clarifications. GPT++ expressions were checked using the original shipped manual-fill interface. Native Python and Rust used the same public/withheld cases. Public problems may have appeared in model training. The study did not measure training contamination or human authoring time.\n")
    print("| Task | Qwen GPT++ | Qwen Python | Qwen Rust | StarCoder2 GPT++ | StarCoder2 Python | StarCoder2 Rust |")
    print("|---|---|---|---|---|---|---|")
    for task in tasks:
        scores = []
        for model in study.MODELS:
            for lang in ("gpp","python","rust"):
                row = index["trial",f"{model}/{task.name}/{lang}"]
                scores.append("correct" if row["accepted"] else "wrong" if row["score"] else "failed public/type gate")
        print(f"| {task.name} | "+" | ".join(scores)+" |")
    print("\n## Search effort\n")
    print("| Task | Minimum GPT++ candidates | Public contract executions for guidance | Guidance value vectors | Minimum-mode value vectors | Numeric hypotheses | Portable value vectors | Portable branch comparisons | Portable public-fitting roots |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for t in tasks:
        rec = compiler("minimum",t)["report"]
        gs = rec.get("guidance",{})
        ps = shared(t)["stats"]
        ms = rec.get("selection",{})
        print(f"| {t.name} | {rec.get('tested',0)} | {gs.get('contract_runs',0)} | {gs.get('value_vectors',0):,} | {ms.get('value_vectors',0):,} | {ms.get('numeric_hypotheses',0):,} | {ps['vector_evaluations']:,} | {ps['partition_tests']:,} | {ps['root_checks']} |")
    print("\nThe larger portable control separately spent 152,192 operations per task. Its first-pass and minimum selectors published six and five wrong expressions respectively. [Larger portable results](expanded-results.md)\n\nWork counters are specific to each implementation. All three portable policies reuse the same search. Exact proposals, compiler reports and score digests are in the [trial archive](results.jsonl). [Reproduction guide](README.md)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive",type=Path)
    report(parser.parse_args().archive)
