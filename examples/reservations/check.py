"""Build real libraries and exercise both unmodified clients in fresh processes."""

import argparse
import concurrent.futures
import json
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "booking.gpp"
SUFFIX = ".dylib" if sys.platform == "darwin" else ".so"
HISTORY = ("reserve", "A", "reserve", "B", "cancel", "A", "cancel", "A")
REPEAT_CANCEL = "if booking == Booking::Cancelled { return Change(available, booking, Outcome::Ok); }"


def replace_repeat_branch(text, expression, replacement):
    assert text.count(REPEAT_CANCEL) == 1
    return text.replace(REPEAT_CANCEL, REPEAT_CANCEL.replace(expression, replacement))


def sketch_source(which):
    if which == "available":
        return replace_repeat_branch(
            SOURCE.read_text(), "Change(available,", "Change(?released: I64,"
        )
    return replace_repeat_branch(SOURCE.read_text(), "Outcome::Ok", "?repeat: Outcome")


def run(*args, code=0):
    result = subprocess.run(args, text=True, capture_output=True, timeout=45)
    if result.returncode != code:
        raise RuntimeError(
            f"{args}: expected {code}, got {result.returncode}\n{result.stdout}{result.stderr}"
        )
    return result.stdout


def rust_client(work):
    client = work / "booking-rust"
    run(
        "rustc",
        "--edition=2024",
        HERE / "booking.rs",
        "-L",
        f"native={work}",
        "-C",
        f"link-arg=-Wl,-rpath,{work}",
        "-o",
        client,
    )
    return client


def python(work, database, *args, code=0):
    return json.loads(
        run(
            sys.executable,
            HERE / "booking.py",
            "--lib",
            work / ("libbooking" + SUFFIX),
            "--db",
            work / database,
            *args,
            code=code,
        )
    )


def durable_sequence(work, database):
    python(work, database, "init", "2")
    for action, booking in zip(HISTORY[::2], HISTORY[1::2]):
        python(work, database, action, booking)
    return python(work, database, "status")


def check_reservations(gpp, work):
    report = json.loads(run(gpp, "verify", SOURCE, "--format=json"))
    assert report["status"] == "passed"
    assert [row["checked"] for row in report["contracts"]] == [4, 16, 64, 256, 1]
    print("Finite verification passed 340 ordered histories and one sold-out contract.")

    text = SOURCE.read_text()
    sketch = work / "booking-sketch.gpp"
    sketch.write_text(sketch_source("outcome"))
    holes = json.loads(run(gpp, "holes", sketch, "--function", "transition"))
    flags = ["--hole", "repeat", "--expect", holes["revision"]]
    decision = json.loads(run(gpp, "complete", sketch, *flags))
    assert decision["status"] == "verified" and decision["selected"] == "Outcome::Ok"
    assert decision["verification"]["checked"] == 341
    completed = work / "completed.gpp"
    completed.write_text(run(gpp, "complete", sketch, *flags, "--stdout"))
    assert completed.read_bytes() == SOURCE.read_bytes()
    print(
        f"Typed outcome completion checked {decision['tested']} expressions and recreated the shipped module byte-for-byte."
    )
    quantity = work / "available-sketch.gpp"
    quantity.write_text(sketch_source("available"))
    report = json.loads(run(gpp, "complete", quantity, "--hole", "released", code=3))
    assert report["status"] == "ambiguous" and "selected" not in report
    question = report["question"]
    assert (
        question["inputs"]["booking"] == "Booking::Cancelled"
        and question["inputs"]["reserve"] is False
    )
    outcomes = [
        answer["outcome"]["result"]["available"] for answer in question["alternatives"]
    ]
    assert outcomes[0] != outcomes[1]
    print(
        f"An open quantity produced a question at {question['inputs']['available']} free seats: {outcomes}."
    )

    broken = work / "double-release.gpp"
    broken.write_text(
        replace_repeat_branch(text, "Change(available,", "Change(available + 1,")
    )
    red = subprocess.run(
        [gpp, "verify", broken, "--format=json"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert red.returncode != 0, red.stdout
    failed = next(
        r
        for r in json.loads(red.stdout)["contracts"]
        if r["status"] == "counterexample"
    )
    assert failed["counterexample"]["args"] == [0, 1, 1]

    shared = work / ("libbooking" + SUFFIX)
    run(gpp, "library", broken, "-o", shared)
    client = rust_client(work)
    snapshot = durable_sequence(work, "red.db")
    assert snapshot == {
        "available": 2,
        "capacity": 2,
        "bookings": {"A": "cancelled", "B": "active"},
    }
    assert "cancel A ok available=2" in run(client, "2", *HISTORY)
    run(gpp, "library", completed, "-o", shared)
    snapshot = durable_sequence(work, "green.db")
    assert snapshot == {
        "available": 1,
        "capacity": 2,
        "bookings": {"A": "cancelled", "B": "active"},
    }
    rust = run(client, "2", *HISTORY)
    assert rust.splitlines() == [
        "reserve A ok available=1",
        "reserve B ok available=0",
        "cancel A ok available=1",
        "cancel A ok available=1",
        "booking A cancelled",
        "booking B active",
    ]
    print(
        "Both unchanged clients reproduced the extra release and passed after replacing the library."
    )

    def green(action, booking, code=0):
        return python(work, "green.db", action, booking, code=code)

    assert green("reserve", "A", 2)["outcome"] == "closed_booking"
    assert green("cancel", "missing", 2)["outcome"] == "unknown_booking"
    assert green("reserve", "B")["available"] == 1
    assert green("reserve", "C")["available"] == 0
    assert green("reserve", "D", 2)["outcome"] == "sold_out"
    assert python(work, "green.db", "status")["bookings"] == {
        "A": "cancelled",
        "B": "active",
        "C": "active",
    }
    rust = run(
        client,
        "1",
        "cancel",
        "unknown",
        "reserve",
        "A",
        "reserve",
        "A",
        "reserve",
        "B",
        "cancel",
        "A",
        "reserve",
        "A",
        code=2,
    )
    assert rust.splitlines() == [
        "cancel unknown unknown_booking available=1",
        "reserve A ok available=0",
        "reserve A ok available=0",
        "reserve B sold_out available=0",
        "cancel A ok available=1",
        "reserve A closed_booking available=1",
        "booking A cancelled",
    ]

    python(work, "contended.db", "init", "1")

    def contend(index):
        cmd = [
            sys.executable,
            HERE / "booking.py",
            "--lib",
            shared,
            "--db",
            work / "contended.db",
            "reserve",
            f"guest-{index}",
        ]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        assert p.returncode in (0, 2), p.stderr
        return json.loads(p.stdout)["outcome"]

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        outcomes = list(pool.map(contend, range(6)))
    assert sorted(outcomes) == ["ok"] + ["sold_out"] * 5
    snapshot = python(work, "contended.db", "status")
    assert snapshot["available"] == 0 and len(snapshot["bookings"]) == 1
    print(
        "Six independent Python processes competed for the last seat. Exactly one booked it."
    )


def check_c_abi(gpp, work):
    source = work / "abi.gpp"
    source.write_text("""module demo.abi;
pub fn minimum() -> I64 !{} { return -9223372036854775808; }
pub fn truth(b: Bool) -> Bool !{} { return !b; }
pub fn unit_value(u: Unit) -> Unit !{} { return u; }
pub fn divide(n: I64, d: I64) -> I64 !{} { return n / d; }
pub fn range(v: I64, lo: I64, hi: I64) -> I64 !{} { return clamp(v, lo, hi); }
fn hidden() -> I64 !{} { return 7; }
pub fn main() -> I64 !{} { return hidden(); }
""")
    header = run(gpp, "library", source, "--header")
    assert "gpp_v1_hidden" not in header and "gpp_v1_main" not in header
    (work / "abi.h").write_text(header)
    (work / "client.c").write_text("""#include "abi.h"
#include <assert.h>
#include <stddef.h>
int main(void) {
    int64_t value = 27;
    assert(gpp_v1_divide(INT64_MIN, -1, &value) == 1 && value == 27);
    assert(gpp_v1_divide(1, 0, &value) == 2 && value == 27);
    assert(gpp_v1_range(5, 8, 7, &value) == 3 && value == 27);
    assert(gpp_v1_truth(2, &value) == 4 && value == 27);
    assert(gpp_v1_unit_value(-1, &value) == 4 && value == 27);
    assert(gpp_v1_minimum(NULL) == 4);
    assert(gpp_v1_minimum(&value) == 0 && value == INT64_MIN);
    assert(gpp_v1_truth(0, &value) == 0 && value == 1);
    assert(gpp_v1_truth(1, &value) == 0 && value == 0);
    assert(gpp_v1_unit_value(0, &value) == 0 && value == 0);
    assert(gpp_v1_divide(-19, 4, &value) == 0 && value == -4);
    return 0;
}
""")
    for level in ("-O0", "-O2"):
        run(gpp, "library", source, level, "-o", work / ("libabi" + SUFFIX))
        run(
            "cc",
            "-std=c11",
            work / "client.c",
            "-L",
            work,
            "-labi",
            f"-Wl,-rpath,{work}",
            "-o",
            work / "client",
        )
        run(work / "client")
    print(
        "Generated C header and both library optimization levels passed scalar and fault checks."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpp", type=Path, default=Path("target/debug/gpp"))
    parser.add_argument(
        "--sketch",
        nargs="?",
        const="outcome",
        choices=("outcome", "available"),
        help="print the module with one repeat-cancellation field left open",
    )
    args = parser.parse_args()
    if args.sketch:
        print(sketch_source(args.sketch), end="")
        return
    gpp = args.gpp.resolve()
    with tempfile.TemporaryDirectory(prefix="gpp-reservations-") as directory:
        work = Path(directory)
        check_c_abi(gpp, work)
        check_reservations(gpp, work)


if __name__ == "__main__":
    main()
