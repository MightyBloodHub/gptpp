# Contract-gated edits

The opt-in driver searches a typed hole, checks public examples, and verifies named finite or symbolic obligations on the checked edit. It can return a compiler proposal without a model call. A failing property produces a replayed input, the expression’s actual runtime observations and the violated rule for one repair attempt. If two surviving proposals differ, a supplied public reference may answer one question. The JSON records the source revision, exact contract declarations and domains, unresolved checks, model usage and final decision. The existing compiler commands keep their defaults. [Driver](../../tools/acceptance.py) · [Example invocation and receipt format](../../examples/makes10/README.md)

Read the [short results report](results.md) for the engineering decision and the scoped repair outcomes.

## Historical baseline and development

The checkout started clean, with HEAD and origin/master both at `0ad5a404b0f9108a3a5786325782eee663c57f43`. Run the historical decision replay from the repository root. It checks the archive fingerprint and reads the stored responses and independent scores. Add `--json` for a machine-readable decision table.

```sh
python3 -B bench/search-confirmation/replay_decisions.py
```

Piecewise alone solved 4/11, direct Qwen in GPT++ solved 7/11, and accepting all seven piecewise selections and using Qwen for the other four solved 5/11. The fallback recovered `more20`. It lost Qwen’s correct `makes10` and `nearHundred` answers, and published a wrong `posNeg` where Qwen abstained. The historical full-width proofs for `specialEleven` and `sumDouble` were written after scoring. The prior matched stateful study had 2/8 correct in each language. [Eleven exercises](../search-confirmation/results.md) · [Proof scope](../search-confirmation/proofs.md) · [Earlier paired stateful study](../stateful/paired.md)

| Development case | Observation |
|---|---|
| `makes10` | The old edit passed 24 examples. Swapping the arguments changed the result on (−5, 10) and (10, −5). The correct reference passed all 576 symmetry assignments and the exact bounded proof. A weak property covering only ten on the right accepted the wrong program. Qwen’s one repair fixed ten on the left but lost ten on the right. The gate withheld it. [Development capture](../../examples/makes10/development.json) |
| `posNeg` | The archived GPT++ model answer failed a public example. The compiler’s selected answer passed the examples but violated the sign rule on (−8, 0, true). Its return value was true even though zero has neither sign. The new 193-input/31-output-token Qwen repair passed the examples and failed the same property. The workflow abstained. [Repair request and response](dev_posneg_capture.json) |
| Reservation reopen | One seat, then reserve A, cancel A, reserve B, reopen A. The defective component reports success with both IDs active. The corrected library reports sold out with A cancelled and B active through both unchanged clients. The verifier exhausted 252 shorter histories first. [Run the development demo](../../examples/reservations/README.md#reopen-a-cancelled-booking) |

Both model repair demonstrations replay offline with a release build. The `makes10` proof also needs Z3.

```sh
python3 -B examples/makes10/demo.py
python3 -B bench/checked_edits/dev_posneg.py
```

## Run the comparison

The collector requires Python 3.11+, the repository’s Rust toolchain, strict mypy in `target/empirical-venv`, and a local Ollama server with the Qwen digest in the protocol. From the repository root, run the following command with a new output directory. It verifies the frozen sources, builds the release compiler, calibrates the contracts, runs all 90 assignments and closes the decision log before separate scoring. It then runs the matched-helper check on those assignments. The two results are written to `primary/results.md` and `matched_helpers/results.md`. [Python environment setup](../empirical/README.md#reproduce) · [Frozen protocol](protocol.md) · [Source fingerprints](freeze.json)

```sh
python3 -B bench/checked_edits/compare.py target/new-checked-edits
```

Use the archived run for an offline replay with the captured compiler binary fingerprint and the same native validation tools. Replay checks the exact prompts and public decisions without issuing a model call. The scorer’s raw output records the first divergent caller-visible result for each wrong publication. [Fresh results](run/results.md) · [Independent scoring](run/scores.json)

```sh
python3 -B bench/checked_edits/replay_run.py bench/checked_edits/run
```

The frozen GPT++ prompt advertises an `abs` helper absent from its sketch. Python and Rust supply it. The separately labeled matched-helper replay tests this discrepancy on the same assignments. It cannot serve as a second independent sample. [Matched-helper protocol](matched_protocol.md) · [Matched-helper results](matched_run/results.md)

## Regression commands

```sh
cargo test --locked --offline
cargo build --release --locked --offline
python3 -B tools/test_acceptance.py
python3 -B bench/search-confirmation/test_replay_decisions.py
python3 -B bench/checked_edits/test_study.py
```

The ambiguity regression runs a real compiler-generated question. Both `x` and `y` pass the diagonal property, and the witness lies off the diagonal. Without a reference the driver abstains. With an authorized reference it charges one question and publishes the matching expression. Other regressions exercise an unsupported proof, a timeout, finite-budget exhaustion, a wrong expression that satisfies its stated weak contract, and all eleven historical starters and references. [Acceptance tests](../../tools/test_acceptance.py)
