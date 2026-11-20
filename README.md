# GPT++

**A language made by AI, for AI.** GPT++ is a free and open project. [Project website](https://gptpp.sandoog.co/)

GPT++ is an experimental programming language designed for coding agents. An agent can ask the compiler what an expression did on a particular call, which local values it could use, and which source revision it can safely edit. It can search for a change by specifying examples of the behavior it wants. The same scalar program runs in the offline reference interpreter or compiles to a native executable through LLVM.

**Latest language changes.** GPT++ now supports explicit Boolean-to-integer conversion with `as I64` and checked integer `min`, `max` and `clamp`. These operations let Qwen's saved proposals repair all three new arithmetic tasks, after the earlier compiler rejected them. The selected changes passed 36 withheld tests and 879 additional checks. The operations were chosen after reviewing those failures. [Exact proposals and outcomes](bench/expression/results/compat.md)

Agents can also test a stream of independent expression edits through one revision-bound compiler session. The repair search and distinguishing-input tool use this interface. Across nine workloads, the sum of median command times fell from 28.143 to 1.334 seconds, a 21.10× speedup, with identical menus and questions. [Latency measurements](bench/expression/results/probe.md) · [Runtime and memory](bench/runtime/results.md) · [Batch protocol](docs/scalar-language.md#check-several-candidate-edits-in-one-process) · [Roadmap](ROADMAP.md)

## Quick start

Use the Rust toolchain pinned in [rust-toolchain.toml](rust-toolchain.toml). The compiler has zero third-party Cargo dependencies.

```sh
cargo build --locked --offline
target/debug/gpp check examples/add.gpp
target/debug/gpp run --interpreter examples/add.gpp
```

The example prints `42`. The current language includes checked signed 64-bit integers, booleans, local bindings, functions, conditionals, and loops. [Example source](examples/add.gpp) · [Scalar language reference](docs/scalar-language.md)

### Ask the compiler about a running program

```sh
target/debug/gpp trace examples/add.gpp --function add --call main
```

The JSON identifies `left + right` at bytes `73:85`. It ran once, with `left = 20` and `right = 22`, and returned the integer `42`. The response includes the source revision and the same byte ranges that the checked editor accepts. [Trace protocol](docs/scalar-language.md#trace-a-call)

### Find an edit from examples

Suppose `add` needs to compute a signed difference. Supply one example through its existing caller and two direct calls. This search runs offline.

```sh
cat > target/difference.json <<'JSON'
[
  {"function":"main","args":[],"expected":-2},
  {"args":[-4,-9],"expected":5},
  {"args":[1,0],"expected":1}
]
JSON
python3 tools/repair.py examples/add.gpp --function add \
  --cases target/difference.json --list
```

The search tests 69 edits and returns one candidate, replacing `left + right` with `left - right`. A local model can select or abstain when given a task description. When multiple edits fit, an agent can ask for the input whose expected result would separate the most pairs of candidates. [Behavior-guided authoring](tools/README.md#search-for-an-edit-with-public-examples) · [Distinguishing-input example](tools/README.md#ask-for-an-example-that-distinguishes-candidate-edits)

### Build a native executable

Native builds require LLVM 22.1.8 with `opt` and `clang`, a host linker, and platform C headers. The native path was verified on Apple Silicon macOS. Set `GPP_LLVM_BIN` to the matching LLVM bin directory if the tools are outside the driver's search path.

```sh
target/debug/gpp build -O2 examples/add.gpp -o target/add
./target/add
```

### Try a checked maintenance edit

Start a local Ollama server with `qwen2.5-coder:7b` installed. This example proposes changing `add` to return the larger argument. It checks both a direct call and the existing `main` caller.

```sh
cat > target/add-cases.json <<'JSON'
[
  {"args": [-4, -9], "expected": -4},
  {"function": "main", "args": [], "expected": 22}
]
JSON
python3 tools/propose.py examples/add.gpp --function add --maintenance \
  --task 'Return the larger argument.' --cases target/add-cases.json \
  -o target/larger.body
```

The tool saves the checked fragment, shows the diff, and prints a revision-guarded command to apply it after review. Use `gpp edit` for hand-written edits. [Authoring and preview guide](tools/README.md) · [Compiler edit example](docs/scalar-language.md#preview-a-function-edit)

## Repository guide

| Path | What it contains |
|---|---|
| [src/](src/) | Parser, type checker, interpreter, native backend, and checked editor |
| [spec/](spec/) | Executable scalar grammar |
| [examples/](examples/) and [tests/](tests/) | Example programs, conformance fixtures, and editor tests |
| [tools/](tools/) | Local-model authoring, ordered rules, and caller analysis |
| [bench/](bench/) | Benchmark protocols, raw trials, reports, and replay tools |
| [docs/](docs/) | [Scalar language reference](docs/scalar-language.md) and [long-form design](docs/design.md) |
| [brand/](brand/) | GPT++ logo, digital identity guide, and web theme |
| [website/](website/) | Source and build instructions for the project website |

The [roadmap](ROADMAP.md) records the current priorities. The [contributing guide](CONTRIBUTING.md) covers development setup, verification, and benchmark changes.
