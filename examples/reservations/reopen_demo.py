"""Replay a reservation policy change through the existing Python and Rust clients."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from check import HERE, SOURCE, SUFFIX, run, rust_client

ACTIONS = (("reserve", "A"), ("cancel", "A"), ("reserve", "B"), ("cancel", "B"))
LOCAL = (0, 1, 0)
CORRECT = "Change(available, booking, Outcome::SoldOut)"
WRONG = ("if booking == Booking::Cancelled { Change(available, Booking::Active, Outcome::Ok) } "
         f"else {{ {CORRECT} }}")


def sketch_text():
    text = SOURCE.read_text()
    closed = "        if booking == Booking::Cancelled { return Change(available, booking, Outcome::ClosedBooking); }\n"
    assert text.count(closed) == text.count(CORRECT) == 1
    # Reopening uses ordinary reservation logic. The only editable expression is
    # the reply when the caller has no seat and the venue is already full.
    text = text.replace(closed, "").replace(CORRECT, "?full: Change")
    start = text.index("// An independent specification reads the history:")
    end = text.index("contract sold_out()", start)
    return text[:start] + (HERE / "reopen.contracts.gpp.inc").read_text() + "\n" + text[end:]


def complete(gpp, sketch, catalog, fragment, work, *, rejected):
    flags = ["--hole", "full", "--fill", fragment, "--expect", catalog["revision"]]
    report = json.loads(run(gpp, "complete", sketch, *flags, code=int(rejected)))
    assert report["status"] == ("rejected" if rejected else "verified"), report
    # A rejected fill cannot publish. The checked editor can still materialize
    # a temporary reproducer bound to the very same revision and expression.
    site, = catalog["holes"]
    span = f"{site['start_byte']}:{site['end_byte']}"
    if rejected:
        contents = run(gpp, "edit", sketch, "--function", "transition", "--at", span,
                       "--expr", fragment, "--expect", catalog["revision"], "--stdout")
    else:
        contents = run(gpp, "complete", sketch, *flags, "--stdout")
    candidate = work / (fragment.stem + ".gpp")
    candidate.write_text(contents)
    assert run(gpp, "revision", candidate).strip() == report["verification"]["revision"]
    return candidate, report["verification"]


def cli(*args):
    result = subprocess.run(args, text=True, capture_output=True, timeout=45)
    if result.returncode not in (0, 2):
        raise RuntimeError(f"{args}: {result.stdout}{result.stderr}")
    return result.returncode, result.stdout


def client_histories(work, shared, rust, capacity, word, database):
    python = [sys.executable, HERE / "booking.py", "--db", work / database, "--lib", shared]
    run(*python, "init", str(capacity))
    histories = {"python": [], "rust": []}
    pairs = []
    rejected = False
    for action in word:
        pair = ACTIONS[action]
        pairs.extend(pair)
        code, output = cli(*python, *pair)
        reply = json.loads(output)
        state = json.loads(run(*python, "status"))
        assert (code == 2) == (reply["outcome"] != "ok")
        assert reply["available"] == state["available"]
        assert reply["state"] == state["bookings"].get(pair[1], "unseen")
        histories["python"].append(dict(state, outcome=reply["outcome"]))

        # Rust owns its ledger in memory. Re-run each prefix to read both IDs
        # from its final snapshot, including the step just before the violation.
        code, output = cli(rust, str(capacity), *pairs)
        lines = output.splitlines()
        name, booking, outcome, free = lines[len(pairs) // 2 - 1].split()
        assert (name, booking) == pair and free.startswith("available=")
        rejected |= outcome != "ok"
        assert (code == 2) == rejected
        bookings = {}
        for line in lines[len(pairs) // 2:]:
            tag, booking, status = line.split()
            assert tag == "booking"
            bookings[booking] = status
        histories["rust"].append(dict(capacity=capacity, available=int(free.split("=")[1]),
                                      bookings=bookings, outcome=outcome))
    return histories


def expected(gpp, candidate, capacity, word):
    padded = [*word, *([4] * (4 - len(word)))]
    trace = json.loads(run(gpp, "trace", candidate, "--function", "expected", "--call", "expected",
                           str(capacity), *map(str, padded)))
    result = trace["result"]
    bookings = {key.upper(): result[key].split("::")[1].lower() for key in ("a", "b")
                if result[key] != "Booking::Unseen"}
    outcomes = {"Outcome::Ok": "ok", "Outcome::SoldOut": "sold_out", "Outcome::UnknownBooking": "unknown_booking"}
    return dict(capacity=capacity, available=result["available"], bookings=bookings, outcome=outcomes[result["last"]])


def demo(gpp, work):
    sketch = work / "reopen.gpp"
    sketch.write_text(sketch_text())
    catalog = json.loads(run(gpp, "holes", sketch, "--function", "transition"))
    fragments = [work / f"{name}.expr" for name in ("incorrect", "corrected")]
    shared = work / ("libbooking" + SUFFIX)
    rust = None
    candidates = []
    for fragment, expression, rejected in zip(fragments, (WRONG, CORRECT), (True, False), strict=True):
        fragment.write_text(expression)
        candidate, report = complete(gpp, sketch, catalog, fragment, work, rejected=rejected)
        if rejected:
            rows = report["contracts"]
            assert [(r["name"], r["status"], r["checked"]) for r in rows[:-1]] == [
                ("local_reopen", "passed", 1), ("one_step", "passed", 12),
                ("two_steps", "passed", 48), ("three_steps", "passed", 192)]
            failed = rows[-1]
            assert failed["name"] == "four_steps" and failed["status"] == "counterexample"
            capacity, *word = failed["counterexample"]["args"]
            expected_history = [expected(gpp, candidate, capacity, word[:i]) for i in range(1, len(word) + 1)]
        else:
            assert report["status"] == "passed" and report["checked"] == 1022, report

        run(gpp, "library", candidate, "-o", shared)
        if rust is None:
            rust = rust_client(work)
        local = client_histories(work, shared, rust, 1, LOCAL, fragment.stem + "-local.db")
        local_expected = [expected(gpp, candidate, 1, LOCAL[:i]) for i in range(1, len(LOCAL) + 1)]
        assert local["python"] == local["rust"] == local_expected
        replay = client_histories(work, shared, rust, capacity, word, fragment.stem + "-witness.db")
        assert replay["python"] == replay["rust"]
        if rejected:
            assert replay["python"][:-1] == expected_history[:-1] and replay["python"][-1] != expected_history[-1]
            actual = replay["python"][-1]
            assert sum(state == "active" for state in actual["bookings"].values()) > capacity
        else:
            assert replay["python"] == expected_history
        candidates.append(dict(source="hand-authored development fixture", expression=expression,
                               verification=report, local_client_agreement=True,
                               witness_client_snapshots={name: states[-1] for name, states in replay.items()}))
    return dict(schema="gpp.reservation-reopen-demo/1", trial_kind="executed development demonstration",
                domain=dict(capacities=[0, 1, 2], actions=ACTIONS, lengths=[1, 2, 3, 4]),
                local_example=dict(capacity=1, steps=[ACTIONS[i] for i in LOCAL], expected=local_expected[-1]),
                counterexample=dict(capacity=capacity, steps=[ACTIONS[i] for i in word],
                                    first_divergence=len(word), previous=expected_history[-2],
                                    expected=expected_history[-1], actual=actual,
                                    rule="Active bookings own exactly one seat each. Reopening requires a free seat."),
                sketch_revision=catalog["revision"], edit_site=catalog["holes"][0], candidates=candidates)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gpp", type=Path, default=HERE.parents[1] / "target/debug/gpp")
    parser.add_argument("--output-dir", type=Path, help="keep the component, corrected library and clients in a new directory")
    args = parser.parse_args()
    if args.output_dir:
        work = args.output_dir.resolve()
        work.mkdir(parents=True, exist_ok=False)
        print(json.dumps(demo(args.gpp.resolve(), work), indent=2))
        return
    with tempfile.TemporaryDirectory(prefix="gpp-reopen-") as directory:
        print(json.dumps(demo(args.gpp.resolve(), Path(directory)), indent=2))


if __name__ == "__main__":
    main()
