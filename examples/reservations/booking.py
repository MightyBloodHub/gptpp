"""Durable reservation CLI. GPT++ supplies transitions; SQLite serializes the ledger."""

import argparse
import ctypes
import json
import sqlite3
import sys
from pathlib import Path

STATES = ("unseen", "active", "cancelled")
OUTCOMES = ("ok", "unknown_booking", "sold_out", "closed_booking", "invalid_input")
MAX_I64 = (1 << 63) - 1


class BookingLibrary:
    def __init__(self, path):
        library = ctypes.CDLL(str(path.resolve()))
        self.functions = []
        for name in ("booking_outcome", "available_after", "booking_after"):
            function = getattr(library, "gpp_v1_" + name)
            word = ctypes.c_int64
            function.argtypes = [word, word, word, ctypes.POINTER(word)]
            function.restype = ctypes.c_int32
            self.functions.append(function)

    def step(self, available, state, reserve):
        values = []
        for function in self.functions:
            result = ctypes.c_int64()
            status = function(available, state, reserve, ctypes.byref(result))
            if status != 0:
                raise ValueError(f"GPT++ checked call failed with status {status}")
            values.append(result.value)
        return values


def command(args):
    library = BookingLibrary(args.lib) if args.action in ("reserve", "cancel") else None
    if args.action == "init" and not 0 <= args.capacity <= MAX_I64:
        raise ValueError("capacity must be a nonnegative I64")
    if args.action in ("reserve", "cancel") and not args.booking:
        raise ValueError("a nonempty booking ID is required")
    if args.action != "init" and not args.db.is_file():
        raise ValueError("initialize the database first")
    with sqlite3.connect(args.db, timeout=15) as db:
        db.execute("BEGIN IMMEDIATE" if args.action != "status" else "BEGIN")
        if args.action == "init":
            db.execute(
                "CREATE TABLE IF NOT EXISTS inventory (id INTEGER PRIMARY KEY CHECK(id = 1), capacity INTEGER NOT NULL, available INTEGER NOT NULL CHECK(available BETWEEN 0 AND capacity))"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS bookings (id TEXT PRIMARY KEY NOT NULL, state INTEGER NOT NULL CHECK(state IN (1, 2)))"
            )
            if db.execute("SELECT 1 FROM inventory").fetchone():
                raise ValueError("database already initialized")
            db.execute(
                "INSERT INTO inventory VALUES (1, ?, ?)", (args.capacity, args.capacity)
            )
            return {
                "outcome": "ok",
                "capacity": args.capacity,
                "available": args.capacity,
            }
        capacity, available = db.execute(
            "SELECT capacity, available FROM inventory WHERE id = 1"
        ).fetchone()
        if args.action == "status" and args.booking is None:
            ledger = {
                key: STATES[value]
                for key, value in db.execute(
                    "SELECT id, state FROM bookings ORDER BY id"
                )
            }
            return {"capacity": capacity, "available": available, "bookings": ledger}
        row = db.execute(
            "SELECT state FROM bookings WHERE id = ?", (args.booking,)
        ).fetchone()
        state = row[0] if row else 0
        if args.action == "status":
            return {"id": args.booking, "state": STATES[state], "available": available}
        outcome, next_available, next_state = library.step(
            available, state, args.action == "reserve"
        )
        if outcome == 0:
            if next_available != available:
                db.execute(
                    "UPDATE inventory SET available = ? WHERE id = 1", (next_available,)
                )
            if next_state != state:
                db.execute(
                    "INSERT INTO bookings VALUES (?, ?) ON CONFLICT(id) DO UPDATE SET state = excluded.state",
                    (args.booking, next_state),
                )
        return {
            "id": args.booking,
            "state": STATES[next_state],
            "available": next_available,
            "outcome": OUTCOMES[outcome],
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument(
        "--lib",
        type=Path,
        default=Path(
            "libbooking.dylib" if sys.platform == "darwin" else "libbooking.so"
        ),
    )
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("init").add_argument("capacity", type=int)
    for name in ("reserve", "cancel"):
        actions.add_parser(name).add_argument("booking")
    actions.add_parser("status").add_argument("booking", nargs="?")
    args = parser.parse_args()
    try:
        result = command(args)
    except (OSError, TypeError, ValueError, sqlite3.Error) as error:
        parser.exit(1, f"{parser.prog}: {error}\n")
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get("outcome", "ok") == "ok" else 2


if __name__ == "__main__":
    sys.exit(main())
