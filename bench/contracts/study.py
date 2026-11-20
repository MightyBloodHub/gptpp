"""Check exact finite-contract witnesses, repair output and matched Python/Rust behavior."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import platform
import subprocess
import sys
from tempfile import TemporaryDirectory

from fixtures import TASKS, oracle


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CANDIDATE_KEYS = ("start_byte", "end_byte", "old", "replacement")


def run(command, *, ok=(0,), timeout=90):
    result = subprocess.run(list(map(str, command)), text=True, capture_output=True, timeout=timeout)
    if result.returncode not in ok:
        raise RuntimeError(f"{command[1:3]} exited {result.returncode}: {result.stderr or result.stdout}")
    return result


def require(condition, message):
    if not condition:
        raise ValueError(message)


def typed_equal(a, b):
    # Python otherwise treats True == 1, while the language's result types are distinct.
    return type(a) is type(b) and a == b


def same_json(a, b):
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def native_literal(value):
    return json.dumps(value)


def comparison_results(task, work):
    """Compile/run the explicit native expressions for every curated patch on the same inputs."""
    cases = task.tuples() + list(task.extra)
    variants = [task.original, *task.menu]
    expressions = len(variants)
    py = ["import json", f"inputs = {cases!r}"]
    rust = ["fn main() {", "std::panic::set_hook(Box::new(|_| {}));"]
    args = ", ".join(task.names)
    arg_types = ["bool" if type(d[0]) is bool else "i64" for d in task.domains]
    parameters = ", ".join(f"{p}: {ty}" for p, ty in zip(task.names, arg_types))
    result_type = "bool" if task.result_type == "Bool" else "i64"
    rust_args = ", ".join("(" + ", ".join(native_literal(v) for v in values) + ")" for values in cases)
    rust.append(f"let inputs: [({', '.join(arg_types)}); {len(cases)}] = [{rust_args}];")
    for index, (_, python_expr, rust_expr) in enumerate(variants):
        py.extend([f"def variant_{index}({args}):", f"    return {python_expr}",
                   "for args in inputs:", f"    try: print(json.dumps(variant_{index}(*args)))",
                   "    except ZeroDivisionError: print('DivisionByZero')"])
        rust.extend([f"fn variant_{index}({parameters}) -> {result_type} {{ {rust_expr} }}",
                     f"for ({args}) in inputs {{",
                     f"   match std::panic::catch_unwind(|| variant_{index}({args})) {{",
                     '      Ok(v) => println!("{}", v),',
                     '      Err(p) => {',
                     '         let msg = p.downcast_ref::<&str>().copied().or_else(|| p.downcast_ref::<String>().map(String::as_str));',
                     '         assert!(msg.is_some_and(|s| s.contains("divide by zero") || s.contains("divisor of zero")));',
                     '         println!("DivisionByZero");',
                     '      }', '   }', '}'])
    rust.append("}")
    pypath, rsp, binary = work / "variants.py", work / "variants.rs", work / "variants"
    pypath.write_text("\n".join(py) + "\n")
    rsp.write_text("\n".join(rust) + "\n")
    run(["rustc", "--edition=2024", "-C", "overflow-checks=yes", rsp, "-o", binary])
    outcomes = {}
    for language, cmd in [("python", [sys.executable, "-I", pypath]), ("rust", [binary])]:
        lines = run(cmd).stdout.splitlines()
        require(len(lines) == expressions * len(cases), f"{language} omitted an input or variant")
        values = [{"fault": text} if text == "DivisionByZero" else {"result": json.loads(text)} for text in lines]
        outcomes[language] = [values[i:i+len(cases)] for i in range(0, len(values), len(cases))]
    require(same_json(outcomes["python"], outcomes["rust"]), "Native Python/Rust behavior differed")
    return outcomes


def patches(gpp, task, source):
    listing = json.loads(run([gpp, "expressions", source, "--function", task.target]).stdout)
    old = task.original[0]
    sites = [e for e in listing["expressions"] if e["text"] == old]
    require(len(sites) == 1, f"Expected one exact occurrence of {old!r}")
    span = sites[0]
    candidates = [dict(start_byte=span["start_byte"], end_byte=span["end_byte"], old=old, replacement=e[0])
                  for e in task.menu]
    return {"schema": "gpp.repair/1", "revision": listing["revision"], "function": task.target,
            "candidates": candidates}


def apply(gpp, task, source, menu, candidate, work):
    span = f"{candidate['start_byte']}:{candidate['end_byte']}"
    fragment = work / "patch.expr"
    fragment.write_text(candidate["replacement"] + "\n")
    result = run([gpp, "edit", source, "--function", task.target, "--at", span, "--expr", fragment,
                  "--expect", menu["revision"], "--stdout"])
    require(result.stdout.endswith(f"contract rule({task.binders}) {{ {task.property} }}\n"),
            "Editing a function changed the contract")
    patched = work / "preview.gpp"
    patched.write_text(result.stdout)
    return patched


def direct(gpp, task, file):
    values = []
    for args in task.tuples() + list(task.extra):
        command = [gpp, "trace", file, "--function", task.target, "--call", task.target, *map(native_literal, args)]
        obj = json.loads(run(command).stdout)
        if "result" in obj:
            values.append({"result": obj["result"]})
        elif "fault" in obj:
            values.append({"fault": obj["fault"]})
        else:
            raise ValueError("Missing interpreter outcome")
    return values


def independent(task, observations):
    domain = task.tuples()
    cases = domain + list(task.extra)
    correct = ["result" in actual and typed_equal(oracle(task, args), actual["result"])
               for args, actual in zip(cases, observations, strict=True)]
    first = next((i for i, passed in enumerate(correct[:len(domain)]) if not passed), None)
    return {"public_pass": all(correct[cases.index(args)] for args in task.public),
            "domain_pass": first is None, "first_bad_index": first,
            "extra_correct": sum(correct[len(domain):]), "extra_total": len(task.extra)}


def verify(gpp, file, budget, *, contract=True):
    args = [gpp, "verify", file, "--budget", str(budget), "--format=json"]
    if contract:
        args.extend(["--contract", "rule"])
    proc = run(args, ok=(0, 1, 3))
    value = json.loads(proc.stdout)
    require(value["schema"] == "gpp.verify/1", "Unexpected verification schema")
    require(value["revision"] == "sha256:" + sha(file.read_bytes()), "Verification has a stale source fingerprint")
    expected_code = {"passed": 0, "counterexample": 1, "incomplete": 3}[value["status"]]
    require(proc.returncode == expected_code and value["budget"] == budget, "CLI exit or budget mismatch")
    return value


def assert_diagnostic(task, observations, judgement, verified):
    first = judgement["first_bad_index"]
    row, = verified["contracts"]
    expected = "passed" if first is None else "counterexample"
    cardinality = len(task.tuples()) if first is None else first + 1
    require(row["name"] == "rule" and row["status"] == verified["status"] == expected, "Wrong decision")
    require(row["checked"] == verified["checked"] == cardinality, "Wrong enumeration count")
    if first is not None:
        obs = observations[first]
        witness = row["counterexample"]
        expected_inputs = dict(zip(task.names, task.tuples()[first], strict=True))
        require(same_json(witness["inputs"], expected_inputs), "Wrong first counterexample tuple")
        if "fault" in obs:
            require(witness.get("fault") == obs["fault"], "Runtime fault was lost")
        else:
            require(witness.get("result") is False, "Expected a false predicate witness")


def normalized(result, work, gpp):
    # Preserve full reports except for ephemeral paths in optional application arguments.
    def norm(obj):
        if isinstance(obj, str):
            return obj.replace(str(work), "<work>").replace(str(gpp), "<gpp>")
        if isinstance(obj, dict):
            return {k: norm(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [norm(v) for v in obj]
        return obj
    return norm(result)


def guided(gpp, task, file, menu, work, *, use_menu, budget):
    output = work / f"guided-{int(use_menu)}-{budget}.expr"
    cmd = [sys.executable, "-B", ROOT / "tools/contract_repair.py", file, "--function", task.target,
           "--gpp", gpp, "--budget", str(budget), "-o", output]
    if use_menu:
        cmd.extend(["--menu", work / "menu.json"])
    proc = run(cmd, ok=(0, 1, 3), timeout=150)
    obj = json.loads(proc.stdout)
    require(obj["schema"] == "gpp.contract-repair/1", "Unexpected repair schema")
    require(obj["baseline"]["revision"] == menu["revision"], "Repair baseline has wrong revision")
    choice = obj["selected"]
    if choice is None:
        require(not output.exists(), "Repair published a fragment without a choice")
    else:
        require(obj["status"] == "verified" and obj["verification"]["status"] == "passed", "Uncertified choice")
        require(output.read_text().strip() == choice["replacement"].strip(), "Saved fragment differs")
    return normalized(obj, work, gpp)


def score_choice(gpp, task, source, menu, candidate, work):
    if candidate is None:
        return None
    patched = apply(gpp, task, source, menu, candidate, work)
    values = direct(gpp, task, patched)
    return {"candidate": candidate, "score": independent(task, values), "observed": values}


def row(gpp, task):
    with TemporaryDirectory(prefix="gpp-contract-bench-") as directory:
        work = Path(directory)
        source = work / "starter.gpp"
        original = task.module()
        source.write_text(original)
        menu = patches(gpp, task, source)
        (work / "menu.json").write_text(json.dumps(menu))
        public = [{"function": task.target, "args": t, "expected": oracle(task, t)} for t in task.public]
        cases_path = work / "examples.json"
        cases_path.write_text(json.dumps(public))
        # Both searches run before scoring any candidates outside their authorized specifications.
        examples = json.loads(run([sys.executable, "-B", ROOT / "tools/repair.py", source,
                                   "--function", task.target, "--gpp", gpp, "--cases", cases_path, "--list"]).stdout)
        budget = len(task.tuples())
        filtered = guided(gpp, task, source, menu, work, use_menu=True, budget=budget)
        synthesized = guided(gpp, task, source, menu, work, use_menu=False, budget=budget)
        insufficient = guided(gpp, task, source, menu, work, use_menu=True, budget=budget-1)
        require(insufficient["status"] == "incomplete" and insufficient["selected"] is None,
                "A short budget did not produce incomplete status")
        require(source.read_text() == original, "A proposal modified the source")
        languages = comparison_results(task, work)
        records = []
        for i, candidate in enumerate([None, *menu["candidates"]]):
            path = source if candidate is None else apply(gpp, task, source, menu, candidate, work)
            values = direct(gpp, task, path)
            require(all(same_json(v[i], values) for v in languages.values()), "GPT++ and baseline outcomes differ")
            evidence = independent(task, values)
            verified = verify(gpp, path, budget)
            assert_diagnostic(task, values, evidence, verified)
            if candidate is not None:
                require(evidence["public_pass"], "Curated candidate failed a supplied example")
            records.append({"id": i, "candidate": candidate, "score": evidence, "observed": values,
                            "verification": verified})
        valid = [r["candidate"] for r in records[1:] if r["score"]["domain_pass"]]
        offered = [{k: c[k] for k in CANDIDATE_KEYS} for c in filtered["candidates"]]
        require(offered == valid, "Contract menu disagrees with independent scorer")
        require(filtered["status"] == ("verified" if len(valid) == 1 else "ambiguous"),
                "Unexpected choice for verified candidates")
        if len(valid) == 1:
            require({k: filtered["selected"][k] for k in CANDIDATE_KEYS} == valid[0], "Wrong verified choice")
        else:
            require(filtered["selected"] is None, "Selected one of multiple bounded-equivalent repairs")
        passing = apply(gpp, task, source, menu, valid[0], work)
        short, exact = verify(gpp, passing, budget-1), verify(gpp, passing, budget, contract=False)
        require(short["status"] == "incomplete" and short["checked"] == budget-1
                and exact["status"] == "passed" and exact["checked"] == budget, "Budget boundary differs")
        public_choice = next(iter(examples["candidates"]), None)
        first = score_choice(gpp, task, source, menu, public_choice, work)
        choice = score_choice(gpp, task, source, menu, synthesized["selected"], work)
        if choice:
            require(choice["score"]["domain_pass"], "Synthesized choice failed independent exhaustive tests")
        return {"task": task.target, "source": original, "revision": menu["revision"], "public_examples": public,
                "domain": [list(d) for d in task.domains], "extra": task.extra, "variants": records,
                "direct_value_sha256": {name: sha(json.dumps(v).encode()) for name, v in
                                         {"gpp": [r["observed"] for r in records], **languages}.items()},
                "example_search": examples, "example_search_choice": first,
                "contract_menu": filtered, "contract_search": synthesized, "contract_search_choice": choice,
                "short_budget_repair": insufficient, "short_budget_verified_patch": short,
                "exact_budget_verified_patch": exact}


def sha(data):
    return sha256(data).hexdigest()


def manifest(gpp):
    paths = [Path(__file__).resolve(), HERE / "fixtures.py", HERE / "protocol.md",
             ROOT / "tools/repair.py", ROOT / "tools/contract_repair.py", ROOT / "tools/propose.py",
             ROOT / "tools/distinguish.py", ROOT / "tools/probe.py", ROOT / "tools/contract_check.py", ROOT / "rust-toolchain.toml",
             *sorted((ROOT / "src").glob("*.rs"))]
    return {"study": "finite-contract-checks-v1", "sources": {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in paths},
            "compiler_sha256": sha(gpp.read_bytes()), "python": platform.python_version(),
            "rustc": run(["rustc", "-V"]).stdout.strip(), "platform": platform.platform()}


def read(path):
    with path.open() as f:
        return json.loads(next(f)), [json.loads(line) for line in f]


def report(path):
    _, rows = read(path)
    require([r["task"] for r in rows] == [t.target for t in TASKS], "Incomplete frozen roster")
    print("# Finite contracts and checked repairs\n")
    print("Three locally authored contracts cover 73 distinct input tuples. Two visible examples per task "
          "admit several wrong edits. We independently executed every curated candidate and starter in GPT++, "
          "Python and Rust and checked all returned values and faults.\n")
    print("| Task | Domain tuples | First starter counterexample | Curated edits passing examples | Edits passing full contract | Contract menu |")
    print("|---|---:|---|---:|---:|---|")
    public = correct = comparisons = 0
    for r in rows:
        v = r["variants"]
        checked = r["exact_budget_verified_patch"]["checked"]
        n = sum(x["score"]["domain_pass"] for x in v[1:])
        event = v[0]["verification"]["contracts"][0]["counterexample"]
        args = ", ".join(native_literal(x) for x in event["inputs"].values())
        witness = f"`({args})`" + (f" {event['fault']}" if "fault" in event else " false predicate")
        print(f"| {r['task']} | {checked} | {witness} | {len(v)-1} | {n} | {r['contract_menu']['status']} |")
        public += len(v)-1
        correct += n
        comparisons += len(v) * (checked + len(r["extra"]))
    print(f"\nThe exact-domain checks rejected {public-correct} of the {public} curated edits that passed their "
          f"sparse examples. All three language implementations agreed on {comparisons} program/input outcomes "
          "per language, including the separate out-of-domain checks.\n")
    print("| Task | First example-search candidate | First certified substitution | Edits tried by contract search |")
    print("|---|---|---|---:|")
    for r in rows:
        first, chosen = r["example_search_choice"], r["contract_search_choice"]
        label = "none" if first is None else "passes full domain" if first["score"]["domain_pass"] else "fails full domain"
        edit = (f"`{chosen['candidate']['old']}` → `{chosen['candidate']['replacement']}`"
                if chosen else r["contract_search"]["status"])
        print(f"| {r['task']} | {label} | {edit} | {r['contract_search']['tested']} |")
    public_full = sum(bool(r["example_search_choice"] and r["example_search_choice"]["score"]["domain_pass"]) for r in rows)
    synthesized = sum(bool(r["contract_search_choice"] and r["contract_search_choice"]["score"]["domain_pass"]) for r in rows)
    print(f"\nThe contract-guided search certified edits on {synthesized}/{len(rows)} tasks. Taking the "
          f"first edit found by the sparse-example search passed the full domain on {public_full}/{len(rows)}. "
          "Those two searches also differ in mutation order and available substitutions. Only the curated-menu "
          "comparison holds the candidate set fixed.")
    print("\nThe two carry edits that pass the declared domain differ outside it. The deliberately capped "
          "candidate misses three of five extra probes. The menu preserves that ambiguity. The synthesis "
          "column reports the first certified candidate in search order.\n")
    print("Across all three tasks, a verified patch checked with a budget one below its domain size returned "
          "incomplete. Raising the budget by one verified the complete domain. Each short-budget repair run "
          "left its output fragment absent. No model calls were made. The study measures bounded correctness "
          "and counterexample reporting. Its hand-authored candidate menus leave model repair accuracy unmeasured.")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    modes = cli.add_mutually_exclusive_group()
    modes.add_argument("--report", action="store_true")
    modes.add_argument("--replay", action="store_true")
    cli.add_argument("--gpp", type=Path, default=ROOT / "target/debug/gpp")
    cli.add_argument("archive", type=Path)
    args = cli.parse_args()
    if args.report:
        report(args.archive)
    else:
        binary = args.gpp.resolve(strict=True)
        meta = manifest(binary)
        rows = [row(binary, t) for t in TASKS]
        if args.replay:
            stored, records = read(args.archive)
            require(stored["sources"] == meta["sources"] and same_json(records, rows), "Replayed outcomes differ")
            print("Replayed all finite domains, counterexamples, menu decisions and independent three-language outputs.")
        else:
            with args.archive.open("x") as f:
                for item in [meta, *rows]:
                    print(json.dumps(item), file=f)
