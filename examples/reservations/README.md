# Reservation ledger

One GPT++ module decides what happens when someone reserves or cancels a seat. The Python CLI stores arbitrary booking IDs in SQLite. The Rust client holds its own ID map in memory. Both call the same compiled component. A repeated cancellation succeeds and releases a seat only on the first call. [Booking module](booking.gpp) · [Python client](booking.py) · [Rust client](booking.rs)

## Run the application

Use a shell at the repository root with Python 3, Rust and the [native build prerequisites](../../README.md). This example uses a new database under `target/reservations`.

```sh
cargo build --locked --offline
mkdir -p target/reservations
case "$(uname -s)" in Darwin) suffix=dylib ;; *) suffix=so ;; esac
shared="target/reservations/libbooking.$suffix"
target/debug/gpp library examples/reservations/booking.gpp -o "$shared"
book() { python3 examples/reservations/booking.py --db target/reservations/demo.db --lib "$shared" "$@"; }
book init 2
book reserve A
book reserve B
book cancel A
book cancel A
book status
```

The final snapshot is `{"available": 1, "bookings": {"A": "cancelled", "B": "active"}, "capacity": 2}`. Each command opens a separate process. SQLite serializes each update with `BEGIN IMMEDIATE` and commits the inventory and ID change together. Run `book status B` to inspect a single ID.

The Rust client takes a capacity followed by action and ID pairs. Its output ends with the same free-seat count and the state of both IDs.

```sh
client_dir="$(pwd)/target/reservations"
rustc --edition=2024 examples/reservations/booking.rs -L "native=$client_dir" \
    -C "link-arg=-Wl,-rpath,$client_dir" -o "$client_dir/booking-rust"
"$client_dir/booking-rust" 2 reserve A reserve B cancel A cancel A
```

| Request | Decision | Free seats |
| --- | --- | --- |
| Reserve a new ID with capacity available | Mark active | Subtract one |
| Reserve an active ID again | Succeed with the same booking | Unchanged |
| Reserve a new ID when sold out | Return `sold_out` and leave the ID unseen | Unchanged |
| Cancel an active ID | Mark cancelled | Add one |
| Cancel a cancelled ID again | Succeed | Unchanged |
| Cancel an unseen ID | Return `unknown_booking` | Unchanged |
| Reserve a cancelled ID | Return `closed_booking` and require a new ID for a new reservation | Unchanged |

The Python CLI exits with status 2 for a domain rejection, writes its decision as JSON and preserves the database. The Rust batch client processes every request and returns status 2 if any request was rejected.

## Complete a typed decision

Generate a sketch from the working module. The only change is the expression that supplies the outcome on a repeated cancellation, now `?repeat: Outcome`.

```sh
python3 examples/reservations/check.py --sketch outcome > target/reservations/sketch.gpp
target/debug/gpp holes target/reservations/sketch.gpp --function transition
target/debug/gpp complete target/reservations/sketch.gpp --hole repeat
target/debug/gpp complete target/reservations/sketch.gpp --hole repeat --stdout > target/reservations/completed.gpp
cmp examples/reservations/booking.gpp target/reservations/completed.gpp
```

Completion selected `Outcome::Ok` and verified all 341 assignments. The emitted module matches the working source byte for byte.

A different sketch leaves the number of free seats open. The finite contracts exercise histories from an empty two-seat inventory. Both `available` and `min(available, 2)` satisfy those contracts. The compiler returns an `ambiguous` report with a concrete question. In the measured run a repeat cancellation with eight seats free produced competing results of eight and two.

```sh
python3 examples/reservations/check.py --sketch available > target/reservations/quantity.gpp
target/debug/gpp complete target/reservations/quantity.gpp --hole released
```

## Verify the behavior

```sh
target/debug/gpp verify examples/reservations/booking.gpp --format=json
python3 examples/reservations/check.py
```

The four history contracts check every ordering of reserve A, cancel A, reserve B and cancel B from an empty two-seat inventory, through lengths one to four. They compare both booking states, the latest outcome and the remaining seats with a specification computed from the action history. The counts are 4, 16, 64 and 256, for 340 histories. One further assignment checks the sold-out decision.

The integration test introduces a double-release defect. The verifier returns the three-step witness reserve A, cancel A, cancel A. Both clients reproduce a separate four-call scenario with B still active and two seats reported free. The test rebuilds the completed library at the same path and runs both unchanged clients again. They report one free seat and preserve B. Six concurrent Python processes also compete for a single seat, and exactly one succeeds. [Integration runner](check.py)

## C ABI

`gpp library FILE --header` emits C declarations for the module’s public functions with scalar signatures, excluding the bootstrap entry. To generate this module’s header, run the following command.

```sh
target/debug/gpp library examples/reservations/booking.gpp --header > target/reservations/booking.h
```

The exported functions are `gpp_v1_available_after`, `gpp_v1_booking_after` and `gpp_v1_booking_outcome`. Each takes the current available count, booking code (unseen 0, active 1, cancelled 2), and reserve flag (reserve 1, cancel 0), followed by an `int64_t *` output pointer. The outcome codes are 0 for success, 1 for an unknown booking, 2 for sold out, 3 for a closed ID and 4 for invalid input. Internal records and enums retain their GPT++ types.

Every exported function returns an `int32_t` ABI status. A successful call writes the output and returns 0. Checked overflow, division by zero and inverted clamp bounds return 1, 2 and 3 respectively. Status 4 means an invalid Bool or Unit input, or a null output pointer. The host’s prior output value survives a failed call. The test compiles a separate C client against a generated header at both native optimization levels.

The ledger models a single inventory of interchangeable seats. The bounded history check covers two named bookings and four actions. The backing SQLite database accepts arbitrary booking IDs and a nonnegative I64 capacity.
