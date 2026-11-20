# Cancellation checks in GPT++, Rust and typed Python

Three verifiers checked the same cancellation rules across the valid signed 64-bit capacity range. Each confirmed all three rules for its implementation and caught a deliberately introduced second seat release. [Recorded tool versions, outcomes and source hashes](results.json)

| Rule | Free seats before the first call | Required result |
| --- | --- | --- |
| Cancel an active booking twice | 0 through 9,223,372,036,854,775,806 | First call releases one seat. Second call preserves the first result. |
| Cancel an already cancelled booking | 0 through 9,223,372,036,854,775,807 | Return success, preserve the state and release zero seats. |
| Cancel an unknown booking | 0 through 9,223,372,036,854,775,807 | Return the unknown-booking outcome and preserve inventory and state. |

GPT++ checks the [shipped transition](../../examples/reservations/booking.gpp) with three [additional contracts](../../examples/reservations/cancellation.proof.gpp.inc). The [Rust](booking.rs) and [Python](booking.py) versions implement the cancellation branch directly. The Rust harnesses use checked I64 addition. The Python port explicitly raises on an increment at the I64 ceiling. Each harness constrains the initial capacity to the domain in the table.

| Implementation | Baseline result | Deliberate double release |
| --- | --- | --- |
| GPT++ with Z3 4.16.0 | Three contracts proved | Returned zero free seats as a failing input for repeated cancellation. The interpreter replayed the failure. |
| Rust with Kani 0.68.0 and CBMC 6.11.0 | Three harnesses verified | Failed the repeated-cancellation equality assertion. |
| Typed Python with CrossHair 0.0.114 | Reported “Confirmed over all paths” on all three postconditions | Returned a false postcondition for repeated cancellation with zero free seats. |

This comparison measures what each verifier reported on three specified properties of straight-line code. The Rust and Python ports were written specifically for this check. The setup measures neither model success nor the effort of authoring each specification. The [matched model study](../stateful/results.md) reports model outcomes and costs separately.

## Reproduce

Install Z3 and put its executable on the command search path. Set up Kani for the host and a Python 3.11 virtual environment. [Kani installation](https://model-checking.github.io/kani/install-guide.html) · [CrossHair contracts](https://crosshair.readthedocs.io/en/latest/contracts.html)

```sh
cargo build --locked --offline
cargo install --locked --version 0.68.0 kani-verifier
kani setup
python3.11 -m venv target/verifier-env
target/verifier-env/bin/python -m pip install crosshair-tool==0.0.114
target/verifier-env/bin/python -B bench/verifiers/compare.py
```

The runner copies source to a temporary directory, checks the original obligations, changes only the already-cancelled branch to release another seat, and checks for a behavioral failure on repeated cancellation. Use `--kani PATH` or `--gpp PATH` to select an executable. Use `--output target/verifier-results.json` to save a run.
