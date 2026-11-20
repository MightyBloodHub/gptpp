"""Compare symbolic verification with independent finite ground truth."""
import argparse
from collections import Counter
from fractions import Fraction
import hashlib
import itertools
import json
import shutil
from pathlib import Path
import subprocess
import tempfile


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
APP = ROOT / "examples/reservations"
MIN, MAX = -(2**63), 2**63 - 1
SCALE = 2**62
INPUTS = list(itertools.product(range(-2, 3), (False, True)))


class Fault(Exception):
    pass


def integer(n):
    if not MIN <= n <= MAX:
        raise Fault("IntegerOverflow")
    return n


def quotient(x, y):
    if y == 0:
        raise Fault("DivisionByZero")
    magnitude = abs(x) // abs(y)
    return integer(-magnitude if (x < 0) != (y < 0) else magnitude)


def remainder(x, y):
    if y == 0:
        raise Fault("DivisionByZero")
    return 0 if y == -1 else x - quotient(x, y) * y


def clamp(x, lo, hi):
    if lo > hi:
        raise Fault("InvalidBounds")
    return min(hi, max(lo, x))


def accept(_):
    return True


def first_fault(x, b, k):
    if x != k:
        return True
    if b:
        keep_both = (integer(MAX + 1), quotient(1, 0))
    else:
        keep_both = (quotient(1, 0), integer(MAX + 1))
    return accept(keep_both)


def nested(x, b, k):
    if b:
        if x == k:
            return (integer(x + 1), "Open")
        return (x, "Closed")
    return (-x, "Closed")


def outcome(predicate, x, b, k):
    try:
        return {"result": predicate(x, b, k)}
    except Fault as fault:
        return {"fault": str(fault)}


# One source template and a separate executable oracle for each property.
# Python evaluates arguments eagerly, and its 'and' / 'or' operators short-circuit.
CASES = {
    "add_max": (
        f"accept({MAX} + (if x == K {{ 1 }} else {{ 0 }}))",
        lambda x, b, k: accept(integer(MAX + int(x == k)))),
    "subtract_min": (
        f"accept({MIN} - (if b && x == K {{ 1 }} else {{ 0 }}))",
        lambda x, b, k: accept(integer(MIN - int(b and x == k)))),
    "mul_edge": (
        f"accept(x * (if b && x == K {{ {SCALE} }} else {{ 1 }}))",
        lambda x, b, k: accept(integer(x * (SCALE if b and x == k else 1)))),
    "eager_discard": (
        "accept(10 / (x - K))",
        lambda x, b, k: accept(quotient(10, x - k))),
    "guarded_div": (
        "x == K || accept(10 / (x - K))",
        lambda x, b, k: x == k or accept(quotient(10, x - k))),
    "signed_quotient": (
        "x / K == TABLE",
        lambda x, b, k: quotient(x, k) == int(Fraction(x, k))),
    "ordered_faults": (
        f"x != K || (if b {{ both({MAX} + 1, 1 / 0) }} else {{ both(1 / 0, {MAX} + 1) }})",
        first_fault),
    "signed_remainder": (
        "x % K == 0 || ((x % K < 0) == (x < 0))",
        lambda x, b, k: remainder(x, k) == 0 or (remainder(x, k) < 0) == (x < 0)),
    "min_remainder": (
        f"accept({MIN} % (if b {{ -1 }} else {{ x - K }}))",
        lambda x, b, k: accept(remainder(MIN, -1 if b else x - k))),
    "min_division": (
        f"x != K || accept({MIN} / (if b {{ -1 }} else {{ 1 }}))",
        lambda x, b, k: x != k or accept(quotient(MIN, -1 if b else 1))),
    "clamp": (
        "clamp(x, K, 1) == min(max(x, K), 1)",
        lambda x, b, k: clamp(x, k, 1) == min(max(x, k), 1)),
    "record_comparison": (
        "choose(x, b, K) == Reply(if b { x } else { -x }, Status::Closed)",
        lambda x, b, k: nested(x, b, k) == ((x if b else -x), "Closed")),
    "discarded_field": (
        "Reply(10 / (x - K), Status::Open).tag == Status::Open",
        lambda x, b, k: (quotient(10, x - k), "Open")[1] == "Open"),
    "lazy_record_projection": (
        "(if x == K { Reply(0, Status::Closed) } else { Reply(10 / (x - K), Status::Open) }).tag == (if x == K { Status::Closed } else { Status::Open })",
        lambda x, b, k: ((0, "Closed") if x == k else (quotient(10, x-k), "Open"))[1]
        == ("Closed" if x == k else "Open")),
}

BASE = """module proof.check;
enum Status { Open, Closed }
record Reply { n: I64, tag: Status }
fn accept(ignored: I64) -> Bool !{} { return true; }
fn both(first: I64, second: I64) -> Bool !{} { return true; }
fn choose(x: I64, b: Bool, k: I64) -> Reply !{} {
    if b {
        if x == k { return Reply(x + 1, Status::Open); }
        return Reply(x, Status::Closed);
    }
    return Reply(-x, Status::Closed);
}
pub fn main() -> I64 !{} { return 0; }
"""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def command(gpp, operation, path, name):
    p = subprocess.run([gpp, operation, path, "--contract", name], text=True,
                       capture_output=True, timeout=30)
    if p.returncode not in (0, 1):
        raise RuntimeError(f"{operation} {name}: {p.stderr} {p.stdout}")
    report = json.loads(p.stdout)
    assert report["revision"] == "sha256:" + digest(path.read_bytes())
    row, = report["contracts"]
    assert row["name"] == name
    assert row["status"] == report["status"]
    assert (p.returncode == 0) == (row["status"] in {"passed", "proved"})
    return row


def source_for(template, k):
    expr = template.replace("K", str(k))
    if "TABLE" in expr:
        # Materialize a second quotient formulation from exact rationals.
        table = str(int(Fraction(2, k))) if k else "0"
        for x in (1, 0, -1, -2):
            q = int(Fraction(x, k)) if k else 0
            table = f"if x == {x} {{ {q} }} else {{ {table} }}"
        expr = expr.replace("TABLE", f"({table})")
    return BASE + "contract property(x: I64 in -2..=2, b: Bool) {\n    " + expr + "\n}\n"


def bounded(gpp, path):
    records = []
    for family, (template, predicate) in CASES.items():
        for k in (-3, -2, -1, 0, 1, 2, 3):
            source = source_for(template, k)
            path.write_text(source)
            expected = {inputs: outcome(predicate, *inputs, k) for inputs in INPUTS}
            failures = [inputs for inputs, result in expected.items() if result != {"result": True}]
            finite = command(gpp, "verify", path, "property")
            proof = command(gpp, "prove", path, "property")
            assert finite["status"] == ("counterexample" if failures else "passed"), (family, k, finite)
            assert proof["status"] == ("refuted" if failures else "proved"), (family, k, proof)
            if failures:
                first = failures[0]
                assert tuple(finite["counterexample"]["args"]) == first
                assert finite["checked"] == INPUTS.index(first) + 1
                assert all(finite["counterexample"].get(key) == value for key, value in expected[first].items())
                witness = proof["counterexample"]
                params = witness["inputs"]
                inputs = params["x"], params["b"]
                assert type(inputs[0]) is int and type(inputs[1]) is bool and inputs in failures
                assert {key: value for key, value in witness.items() if key != "inputs"} == expected[inputs]
            else:
                assert finite["checked"] == len(INPUTS)
            record = {"family": family, "k": k, "source_sha256": digest(source.encode()),
                      "python_outcomes": dict(Counter(r.get("fault", str(r.get("result")).lower())
                                                      for r in expected.values())),
                      "finite_checked": finite["checked"], "proof": proof["status"]}
            if failures:
                record["solver_witness"] = proof["counterexample"]
            records.append(record)
    return records


def production(gpp, path):
    booking = (APP / "booking.gpp").read_bytes()
    obligations = (APP / "cancellation.proof.gpp.inc").read_bytes()
    source = booking + obligations
    # Extend the real postcondition to a ledger with no headroom for the release.
    source += f"\ncontract without_headroom(available: I64 in 0..={MAX}) {{ cancel_twice(available) }}\n".encode()
    path.write_bytes(source)
    finite = {"one_action": 4, "two_actions": 16, "three_actions": 64, "four_actions": 256, "sold_out": 1}
    for name, count in finite.items():
        row = command(gpp, "verify", path, name)
        assert row["status"] == "passed" and row["checked"] == count
    names = [*finite, "active_cancel_twice", "repeat_cancel", "unknown_cancel", "without_headroom"]
    rows = [command(gpp, "prove", path, name) for name in names]
    assert [r["status"] for r in rows] == ["proved"] * 8 + ["refuted"]
    assert rows[-1]["counterexample"] == {"inputs": {"available": MAX}, "fault": "IntegerOverflow"}
    return {"booking_sha256": digest(booking), "obligations_sha256": digest(obligations),
            "source_sha256_with_negative_control": digest(source), "finite_checked": finite,
            "contracts": rows}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gpp", type=Path, default=ROOT / "target/debug/gpp")
    ap.add_argument("--source", nargs=2, metavar=("FAMILY", "K"), help="print a generated program")
    ap.add_argument("--write", action="store_true", help="replace the archived JSON after successful checks")
    args = ap.parse_args()
    if not __debug__:
        ap.error("run with Python assertion checks enabled")
    if args.source:
        family, k = args.source
        if family not in CASES or k not in [str(k) for k in range(-3, 4)]:
            ap.error(f"expected one of {', '.join(CASES)} and a constant in -3..3")
        print(source_for(CASES[family][0], int(k)), end="")
        return
    gpp = args.gpp.resolve()
    solver = subprocess.check_output(["z3", "--version"], text=True).strip()
    with tempfile.TemporaryDirectory() as tmp:
        snapshot = Path(tmp) / "gpp"
        shutil.copy2(gpp, snapshot)
        compiler_hash = digest(snapshot.read_bytes())
        path = Path(tmp) / "check.gpp"
        cases = bounded(snapshot, path)
        booking = production(snapshot, path)
    counts = dict(Counter(case["proof"] for case in cases))
    report = {"schema": "gpp.proof-differential/1", "solver": solver,
              "inputs_per_program": len(INPUTS), "programs": len(cases),
              "python_assignments": len(cases) * len(INPUTS), "symbolic_results": counts,
              "runner_sha256": digest(Path(__file__).read_bytes()), "gpp_sha256": compiler_hash,
              "production": booking, "cases": cases}
    if args.write:
        (HERE / "results.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"{len(cases)} generated contracts, {report['python_assignments']} Python assignments, "
          f"{counts['proved']} proved, {counts['refuted']} refuted. All witnesses replayed.")
    print(f"{solver}. Eight production contracts proved. Headroom control refuted at {MAX}.")


if __name__ == "__main__":
    main()
