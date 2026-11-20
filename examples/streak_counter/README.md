# Recover a model-authored transition and call it from Python

This program comes from the blind state-transition comparison. The state holds the current hit streak and the longest streak since the previous restart. Each Hit increments the current streak and immediately updates the record. Miss clears the current streak, and Restart clears both fields.

The original target had a typed hole in the record update. Qwen2.5-Coder 7B filled it with `max(s.best, s.streak + 1)` on its first call. Four visible contracts specified example sequences. A separately implemented sequence oracle checked the complete state on 1,088 other sequences of up to six events. The scalar `next_field` facade was added after scoring to let a Python client use the native library. [Completed GPT++ module](streak_counter.gpp) · [Matched study and raw trials](../../bench/stateful/README.md)

From the repository root, build the compiler and replay the exact recorded model answer. No live model server is needed. Native linking requires the compiler’s supported LLVM toolchain.

```sh
cargo build --offline --locked
python3 -B examples/streak_counter/replay.py --output-dir target/streak-example
```

The command extracts the response from the published archive, saves the original module and model expression, invokes the compiler's checked fill command, and compares its output to the shipped program. It checks the withheld sequences in the interpreter, compiles an optimized native library, loads it with Python’s `ctypes`, and checks both integer fields after each withheld sequence. Use a new output directory to keep the generated files. Omit `--output-dir` for a temporary replay.

With the recovered files present, the underlying completion command is also available directly.

```sh
target/debug/gpp complete target/streak-example/original.gpp --hole change \
  --fill target/streak-example/model.expr --stdout
```

The ABI facade accepts event codes 0 for Hit, 1 for Miss and 2 for Restart. For the same input state, pass `want_best=false` to read the next streak and `true` to read the next record. The API exports two integer state coordinates; the typed record stays inside GPT++. The independent oracle's tested lengths, finite examples and matched results are documented in the [study protocol](../../bench/stateful/protocol.md).
