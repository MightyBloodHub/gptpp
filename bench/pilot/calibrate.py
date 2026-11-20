"""Run the public shipping-fee calibration with repository-owned fixture code."""

import csv
import subprocess
import sys
import tempfile
from pathlib import Path

PILOT = Path(__file__).resolve().parent
ROOT = PILOT.parent.parent


def run(args):
    outcome = subprocess.run(args, cwd=ROOT, text=True, capture_output=True, timeout=60)
    if outcome.returncode:
        raise SystemExit(f"{args[0]} exited {outcome.returncode}\n{outcome.stderr}")
    return outcome.stdout.splitlines()


def actual_fees(language, source, cases, work):
    calls = []
    for row in cases:
        member, pickup = row["member"], row["pickup"]
        if language == "py":
            member, pickup = member.title(), pickup.title()
        calls.append(f'shipping_fee({row["subtotal_cents"]}, {member}, {pickup})')

    path = work / f"trial.{language}"
    if language == "py":
        path.write_text(source + "\n" + "\n".join(f"print({call})" for call in calls))
        return run([sys.executable, "-I", path])
    if language == "rs":
        prints = "\n".join(f'    println!("{{}}", {call});' for call in calls)
        path.write_text(source + "\nfn main() {\n" + prints + "\n}\n")
        program = work / "trial"
        run(["rustc", "--edition", "2024", path, "-o", program])
        return run([program])

    # The bootstrap ABI returns a single I64. Each case gets its own entry.
    values = []
    for call in calls:
        path.write_text(source + f"\npub fn main() -> I64 !{{}} {{ return {call}; }}\n")
        values.extend(run(["cargo", "run", "--locked", "--offline", "--quiet",
                           "--", "run", "--interpreter", path]))
    return values


def known_repair(language, starter):
    old = "subtotal_cents >= 7500"
    if starter.count(old) != 1:
        raise SystemExit("starter no longer matches the reviewed repair")
    either, both = ("or", "and") if language == "py" else ("||", "&&")
    return starter.replace(old, f"{old} {either} (member {both} subtotal_cents >= 5000)")


def main():
    with (PILOT / "cases.tsv").open(newline="") as table:
        cases = list(csv.DictReader(table, delimiter="\t"))
    changed = [row["case"] for row in cases if row["old_fee"] != row["new_fee"]]
    if not changed or len(changed) == len(cases):
        raise SystemExit("calibration requires both changed and preserved behavior")

    with tempfile.TemporaryDirectory(prefix="gpp-pilot-") as directory:
        work = Path(directory)
        for language in ["py", "rs", "gpp"]:
            starter = (PILOT / f"starter.{language}").read_text()
            repaired = known_repair(language, starter)
            for column, source in [("old_fee", starter), ("new_fee", repaired)]:
                observed = actual_fees(language, source, cases, work)
                if len(observed) != len(cases):
                    raise SystemExit(f"{language} {column} produced {len(observed)} results for {len(cases)} cases")
                for row, actual in zip(cases, observed):
                    if actual != row[column]:
                        raise SystemExit(f"{language} {column} {row['case']}: expected {row[column]}, got {actual}")
            print(f"{language}: starter fails {len(changed)}/{len(cases)} new expectations; "
                  f"known repair passes {len(cases)}/{len(cases)}")
    print("Changed cases: " + ", ".join(changed))


if __name__ == "__main__":
    main()
