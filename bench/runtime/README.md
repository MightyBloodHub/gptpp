# Scalar execution comparison

Run the three correct reference implementations from the historical expression fixtures in GPT++, Rust and Python. Before measuring, execute every reference against all public and withheld tests using the independent evaluator. This uses reference programs, with no model generations.

Each program performs two million target calls in a signed checksum loop. Redis varies clock and idle duration through modulo expressions with the seconds multiplier. FastLED varies level, fraction and fixed mode. Go varies year and elapsed time within the supplied domain. The full generated programs are archived. Require identical checksums for every language and repetition.

Compile GPT++ and Rust at optimization level 2 with checked integer arithmetic. Use the ordinary Python interpreter and record bytecode compilation time. Run three process executions and alternate language order. Record elapsed time including startup and macOS time -l peak resident memory. Report every workload's median and the single build/check time. Tool startup, linking, interpreter runtime, generated native code and host scheduling contribute to these measurements. This is a development microbenchmark, and representative application workloads are still needed.

Build the current compiler, collect a fresh archive, or regenerate the published table from the repository root.

```sh
cargo build --locked --offline
target/empirical-venv/bin/python -B bench/runtime/run.py target/runtime-new.jsonl
python3 -B bench/runtime/run.py --report bench/runtime/results.jsonl
```
