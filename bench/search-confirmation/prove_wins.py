"""Reproduce and symbolically check the two gains over the largest portable minimum-cost arm."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from confirm import HERE, ROOT, corpus, engine, followup, native


OBLIGATIONS = {
    "specialEleven": """
contract whole_domain(n:I64 in 0..=9223372036854775807) {
    transition(n) == (n % 11 == 0 || n % 11 == 1)
}
""",
    "sumDouble": """
fn sum_fits(a:I64, b:I64)->Bool !{} {
    if b > 0 { return a <= 9223372036854775807 - b; }
    if b < 0 { return a >= -9223372036854775808 - b; }
    return true;
}
contract whole_domain(a:I64 in -9223372036854775808..=9223372036854775807,
                      b:I64 in -9223372036854775808..=9223372036854775807) {
    if a == b {
        a < -2305843009213693952 || a > 2305843009213693951 || transition(a,b) == (a+b)*2
    } else {
        !sum_fits(a,b) || transition(a,b) == a+b
    }
}
""",
}


def run(args, expected=0):
    result = subprocess.run(args, capture_output=True, text=True, timeout=90)
    if result.returncode != expected:
        raise ValueError(f"{args} exited {result.returncode}\n{result.stdout}\n{result.stderr}")
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpp", type=Path, default=ROOT / "target/release/gpp")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    archive = [json.loads(s) for s in (HERE/"results.jsonl").read_text().splitlines()]
    native_rows = {r["key"]:r for r in archive if r["kind"]=="native"}
    portable_rows = {r["key"]:r for r in archive if r["kind"]=="portable"}
    gains = [t for t in corpus.TASKS if native_rows["piecewise/"+t.name]["accepted"]
             and not portable_rows["larger/"+t.name]["selections"]["minimum"]["rust"]["accepted"]]
    if {t.name for t in gains} != set(OBLIGATIONS):
        raise ValueError("Proof cases do not match the complete set of paired wins")
    results = {"solver": run(["z3","--version"]).strip(), "tasks": {}}
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        for t in gains:
            # Search only sees the original sketch and public examples.
            sketch = work/"sketch.gpp"
            sketch.write_text(native.gpp(t))
            opts=[args.gpp,"complete",sketch,"--hole","change","--search","piecewise","--limit","256"]
            selected = json.loads(run(opts))["selected"]
            recorded = native_rows["piecewise/"+t.name]["report"]["selected"]
            if selected != recorded:
                raise ValueError(f"{t.name} completion differs from the recorded expression")
            completed = run([*opts,"--stdout"])
            prior = engine.render(followup.reference_tree(t.old),"gpp")
            baseline = sketch.read_text().replace("?change: "+t.result, "("+prior+")")
            proofs = {}
            for name, program, expected in (("completed",completed,0),("starter",baseline,1)):
                path=work/(name+".gpp")
                path.write_text(program+OBLIGATIONS[t.name])
                row=json.loads(run([args.gpp,"prove",path,"--contract","whole_domain","--timeout-ms","30000"],expected))
                proofs[name]=row
            results["tasks"][t.name]={"selected":selected,"module_sha256":hashlib.sha256(completed.encode()).hexdigest(),**proofs}
    report=json.dumps(results,indent=2)+"\n"
    if args.output:
        args.output.write_text(report)
    print(report,end="")


if __name__=="__main__":
    main()
