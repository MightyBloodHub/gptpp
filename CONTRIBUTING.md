# Contributing to GPT++

## Development setup

Build from the repository root using the pinned Rust toolchain. The full conformance suite also needs Python 3 and LLVM 22.1.8 with `opt`, `clang`, a host linker, and platform C headers. Set `GPP_LLVM_BIN` if LLVM is installed outside `PATH` and the Homebrew search locations. Apple Silicon macOS is the verified native environment. Use the [benchmark setup](bench/empirical/README.md) when you need the pinned Python analysis environment or model artifacts.

```sh
cargo build --locked --offline
cargo fmt --all --check
cargo clippy --locked --offline --all-targets -- -D warnings
cargo test --locked --offline
GPP_TEST_NATIVE=1 python3 -B -m unittest discover -s tools -p 'test_*.py'
```

The authoring tests use a loopback model stub and the real compiler. These commands run without Ollama. The Rust conformance test runs programs through both the interpreter and native builds at `-O0` and `-O2`. Fixture comments such as `// result 42` and `// fault DivisionByZero` specify the expected outcome.

If you change the optional caller analyzer, run its additional Rust tests.

```sh
rustc --edition=2024 --test tools/caller_obligation.rs -o target/caller-obligation-tests
target/caller-obligation-tests
```

## Compiler and authoring changes

- Describe the user-visible behavior and show a small example. Update the [scalar reference](docs/scalar-language.md) or [authoring guide](tools/README.md) when the supported behavior changes.
- For changes to language semantics, check agreement between the interpreter and native execution. Consider both resulting values and arithmetic faults.
- For changes to the editor, exercise the actual CLI, including a rejected edit and its effect on the source file when relevant.

## Benchmark changes

Each study documents its task families, public and withheld checks, model and toolchain versions, and acceptance criteria. The archived prompts, replies, token counts, and outcomes support offline verification. Put fresh run output under `target/` while iterating. If a study depends on changes to previously fingerprinted source or fixtures, record a new manifest with the new results and keep the earlier results available for comparison. [Benchmark index and replay commands](bench/README.md)
