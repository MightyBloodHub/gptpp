# GPT++

**A language made by AI, for AI.** GPT++ is a free and open project. [Project website](https://gptpp.sandoog.co/)

GPT++ is an experimental programming language designed for coding agents. Programs can leave an expression open with a name and a type. An agent can ask which values are in scope, search for expressions that satisfy the callers’ contracts, and get a concrete input when two passing completions disagree. Completed programs run independently of a model.

## Piecewise search on eleven external exercises

The opt-in `--search piecewise` mode partitions public observations by a condition and searches for a rule within each group. In the final frozen comparison, it solved **4/11** CodingBat exercises, compared with **1/11** for the preceding native minimum-cost mode and **2/11** for the largest portable minimum-cost search in each of GPT++, typed Python and Rust. Compared with that portable control, piecewise had two paired wins and zero losses. It published seven programs, including three that failed withheld checks. [Complete comparison](bench/search-confirmation/results.md) · [Frozen protocol](bench/search-confirmation/protocol.md)

Reproduce one of the wins from the exact benchmark sketch. Piecewise selected `(n % 11) <= 1` for `specialEleven`. The expression passed all 24 public and 76 withheld nonnegative inputs. After scoring, Z3 proved this repair for every nonnegative I64 and the other paired win, `sumDouble`, for every signed input pair whose specified result fits I64. [Post-scoring proof replay](bench/search-confirmation/proofs.md)

```sh
cargo build --locked --offline
target/debug/gpp complete examples/special_eleven.gpp --hole change --search piecewise --limit 256
```

The automatic searches used zero model calls. In the separate 66-call comparison, Qwen solved 7/11 in each language and StarCoder2 solved none. The earlier nine-family study tied at 1/9 for the previous compiler and default hybrid search. The next 12-exercise study tied at 0/12 across native and portable solvers. [Nine-family results](bench/search/results.md) · [Twelve-exercise results](bench/search-followup/results.md)

## Search from the behavior a program needs

The default `gpp complete` search now runs source contracts to collect observations at a typed hole. It builds and compares intermediate expressions on those values, including integer scaling, offsets and conditional branches. It checks proposed completions against the full source contracts.

```sh
cargo build --locked --offline
target/debug/gpp complete examples/calibration/sketch.gpp --hole rule --search hybrid --limit 32
target/debug/gpp complete examples/calibration/sketch.gpp --hole rule --search minimum --limit 32 \
  --stdout > target/calibrated.gpp
target/debug/gpp verify target/calibrated.gpp
```

In this development example, seven calibration pairs fit `reading * 17 + 5`. They also fit a piecewise formula. Both the previous release and the current grammar-only search found zero passing candidates within the same limit. The new default found both behaviors and returned `ambiguous`, with an input of four and competing predictions of 73 and 158. The explicit minimum-cost policy selects the five-node linear expression and reports the longer alternative that disagrees. The browser demo lets you supply an eighth reading and verify both formulas. [Try the calibration](https://gptpp.sandoog.co/?example=calibration#finite-contracts) · [Hybrid report](examples/calibration/completion.json) · [Minimum-cost report](examples/calibration/minimum.json)

**Nine fresh tasks.** Both the previous and new default search selected a correct program on 1 of 9 families. The new release solved binary prefix accumulation and asked for clarification on a parcel rule the previous release solved. It returned five ambiguity reports and selected one incorrect program. A portable search shared across GPT++, Rust and typed Python selected four correct programs and four wrong ones using its first passing candidate. Requiring probe agreement selected none. In a separate one-call comparison, Qwen solved 3/9 in GPT++ and 4/9 in each of Rust and typed Python. StarCoder2 solved none. [Results and candidate counts](bench/search/results.md) · [Frozen protocol](bench/search/protocol.md)

**Independent follow-up.** The old compiler, hybrid search and minimum-cost search each solved 0/12 externally published CodingBat exercises. None found an expression that passed the public examples, so the shortest-expression policy never reached a selection. The expanded portable search also solved zero. Qwen separately solved 2 in GPT++, 1 in typed Python and 5 in Rust, while StarCoder2 solved none. [Follow-up outcomes](bench/search-followup/results.md) · [Study design](bench/search-followup/protocol.md)

## A reservation component in GPT++, Python and Rust

The GPT++ module owns the booking state and the reserve/cancel decisions. A Python CLI persists arbitrary booking IDs in SQLite. An independent Rust client uses the same native library through a generated C ABI. In both clients, reserving A and B and cancelling A twice leaves B active and exactly one free seat. Cancelling an unseen ID returns an explicit domain error. [Run the application](examples/reservations/README.md) · [Try the booking verifier](https://gptpp.sandoog.co/?example=booking#finite-contracts)

```sh
cargo build --locked --offline
python3 examples/reservations/check.py --sketch outcome > target/sketch.gpp
target/debug/gpp holes target/sketch.gpp --function transition
target/debug/gpp complete target/sketch.gpp --hole repeat
target/debug/gpp verify examples/reservations/booking.gpp
```

The compiler filled `?repeat: Outcome` with `Outcome::Ok` and checked 340 action histories plus a sold-out case. The resulting module matched the shipped code byte for byte. Leaving the free-seat count open produced two behaviors that agree in the two-seat fixture. The compiler asked whether cancelling an already cancelled booking with eight seats free should leave eight or two. [Completion and ambiguity](examples/reservations/README.md#complete-a-typed-decision)

For wider domains, the native `prove` command uses Z3 to check supported contracts symbolically. The combined reservation module proves eight contracts, including repeated cancellation and unknown IDs over the full nonnegative I64 range. The active-booking property excludes the largest I64 value so that releasing one seat fits. [Full-width obligations](examples/reservations/cancellation.proof.gpp.inc) · [Language reference](docs/scalar-language.md)

**Earlier model comparison.** On four state-machine changes attempted by two models, GPT++, typed Python and Rust each passed the same two of eight assignments. The models made 42 calls across 24 assignments. GPT++ used 2,813.5 tokens per accepted change, Python 2,847 and Rust 3,042.5. These totals include failed attempts. The same model-free search solved three of four tasks in every language. GPT++’s separate built-in search solved two. [Run Qwen’s accepted streak update](examples/streak_counter/README.md) · [Matched results](bench/stateful/results.md) · [Protocol and limits](bench/stateful/protocol.md)

## Earlier experiments

**Finite contracts.** A module can name a rule for a function or its callers. Run the verifier to check the complete declared domain or get the first failing input. Contract-guided repair tests expression edits against those same rules. On three development tasks, six of ten hand-written edits passed the visible examples and then failed on another declared input. [Try the live verifier](https://gptpp.sandoog.co/#finite-contracts) · [Measured results](bench/contracts/results.md) · [Verify a contract](docs/scalar-language.md#verify-a-finite-contract) · [Contract-guided repair](tools/README.md#repair-an-expression-against-source-contracts)

**Scalar operations.** GPT++ supports explicit Boolean-to-integer conversion with `as I64` and checked integer `min`, `max` and `clamp`. These operations let Qwen's saved proposals repair all three new arithmetic tasks, after the earlier compiler rejected them. The selected changes passed 36 withheld tests and 879 additional checks. The operations were chosen after reviewing those failures. [Exact proposals and outcomes](bench/expression/results/compat.md)

Agents can also test a stream of independent expression edits through one revision-bound compiler session. The repair search and distinguishing-input tool use this interface. Across nine workloads, the sum of median command times fell from 28.143 to 1.334 seconds, a 21.10× speedup, with identical menus and questions. [Latency measurements](bench/expression/results/probe.md) · [Runtime and memory](bench/runtime/results.md) · [Batch protocol](docs/scalar-language.md#check-several-candidate-edits-in-one-process) · [Roadmap](ROADMAP.md)

## Quick start

Use the Rust toolchain pinned in [rust-toolchain.toml](rust-toolchain.toml). The compiler has zero third-party Cargo dependencies.

```sh
cargo build --locked --offline
target/debug/gpp check examples/add.gpp
target/debug/gpp run --interpreter examples/add.gpp
```

The example prints `42`. The language supports checked signed 64-bit integers, booleans, records, enums, local bindings, functions, conditionals and loops. [Example source](examples/add.gpp) · [Scalar language reference](docs/scalar-language.md)

### Check a rule over every input in its domain

The sample queue has eight slots. Its contract says a new item fits exactly when adding it keeps occupancy at or below eight.

```gpp
contract respects_capacity(queued: I64 in 0..=8) {
    can_admit(queued) == (queued + 1 <= 8)
}
```

```sh
target/debug/gpp verify examples/capacity.gpp --contract respects_capacity --format=json
```

This checks nine queue sizes, including the full queue. The reference walks through a one-character edit that admits a ninth item and shows how to reproduce the verifier’s counterexample. [Full program](examples/capacity.gpp) · [Walkthrough](docs/scalar-language.md#verify-a-finite-contract)

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
