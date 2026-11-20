# GPT++

**A language made by AI, for AI.** GPT++ is a free and open project. [Project website](https://gptpp.sandoog.co/)

GPT++ is an experimental programming language and toolchain for AI-assisted software maintenance. The project measures how much model work it takes to produce a change that passes independent tests. The `gpp` compiler checks a single source module, runs it in a reference interpreter, and builds native executables through LLVM. The compiler runs offline. An optional local-model tool proposes checked edits to a selected function.

**Project status.** The scalar compiler and maintenance tools are usable. The research target is a repeatable 20% reduction in tokens per accepted edit against strong Python and Rust workflows. That target remains open. [Roadmap](ROADMAP.md) · [Benchmark charts and data](bench/expression/README.md#charts-and-data)

## Quick start

Use the Rust toolchain pinned in [rust-toolchain.toml](rust-toolchain.toml). The compiler has zero third-party Cargo dependencies.

```sh
cargo build --locked --offline
target/debug/gpp check examples/add.gpp
target/debug/gpp run --interpreter examples/add.gpp
```

The example prints `42`. The current language includes checked signed 64-bit integers, booleans, local bindings, functions, conditionals, and loops. [Example source](examples/add.gpp) · [Scalar language reference](docs/scalar-language.md)

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
