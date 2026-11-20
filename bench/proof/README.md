# Differential checks for symbolic verification

The archived run compared 98 generated GPT++ contracts with an independent Python oracle and the GPT++ finite verifier. Z3 4.16.0 proved 53 contracts and refuted 45. All 45 solver witnesses reproduced the independently predicted false result or arithmetic fault. [Per-contract results](results.json)

## Generated programs

The runner generates 14 families with seven constants from −3 through 3. Each program takes an integer from −2 through 2 and a Boolean. Python evaluates all 980 assignments. Its checked-arithmetic functions use unbounded integers to model I64 overflow, signed division and remainder. A separate exact-rational calculation supplies the expected signed quotients embedded in the generated source. The input constants include both ends of the full I64 range. [Generator and oracle](check.py)

| Python result | Assignments |
| --- | ---: |
| True | 879 |
| False | 5 |
| Division by zero | 50 |
| Integer overflow | 26 |
| Invalid clamp bounds | 20 |

The cases exercise eager calls and constructor fields, ordered faults, lazy guards, nested branches, enum tags, field projection and record equality. The finite verifier stops at its first failing tuple. It evaluated 759 assignments across the 98 programs and agreed with Python on each passing domain and each first counterexample. The symbolic command independently chose a witness for each refutation. The runner checks that assignment and its fault or Boolean result against the Python table.

## Production booking checks

The same run compiled the reservation component together with its cancellation obligations. Z3 proved all eight contracts. Finite execution also checked the 340 histories of one to four actions and the sold-out case. The three wide integer properties cover cancelling an active booking twice, repeating a cancellation, and cancelling an unknown booking. [Production transition](../../examples/reservations/booking.gpp) · [Cancellation obligations](../../examples/reservations/cancellation.proof.gpp.inc)

The negative control adds one input to the active-booking domain. At 9,223,372,036,854,775,807 free seats, releasing a seat overflows I64. Z3 produced that input and the interpreter reproduced `IntegerOverflow`. Only the temporary test module includes the extra obligation.

## Replay

Install Z3 on the command search path. Run from the repository root with Python 3 and the repository's Rust toolchain.

```sh
cargo build --locked --offline
python3 bench/proof/check.py
```

The following commands show how to inspect one generated program and execute both checks.

```sh
python3 bench/proof/check.py --source signed_quotient -2 > target/proof-case.gpp
target/debug/gpp verify target/proof-case.gpp
target/debug/gpp prove target/proof-case.gpp
```

Use `--gpp PATH` to select a compiler and `--write` to regenerate the archived JSON after a successful run. The JSON records the solver version, the generator and binary digests, the source digest and outcome for each generated program, and the booking source digests. Different solver builds may choose different valid counterexamples.

These differential checks cover the generated families and the stated booking properties. The Python oracle is an independent implementation of the tested operations. The compiler's concrete and symbolic paths share a parser and type checker. The run supplies regression evidence for the translation. A proof result also depends on the translation and solver being correct.
