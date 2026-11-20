# Final piecewise-search confirmation

This study froze eleven external scalar tasks from two contiguous slices of CodingBat before the implementation team saw the selections. A pure native function has one typed expression hole, 24 public input/output examples and a predetermined independent scoring grid. Source rules and their paired languages are available for inspection. [Results](results.md) · [Original specifications](sources.md) · [Trial archive](results.jsonl) · [Pre-inference protocol](protocol.md) · [Freeze record](freeze.json)

Four native automatic arms compare the previous shipped compiler, its strict guided successor, minimum-cost selection and piecewise selection. A separate solver renders the same selected expressions into GPT++, typed Python and Rust. It applies first passing, consensus and minimum-cost consensus at three search sizes. Every native and portable arm uses a 256-completed-root limit and a 30-second per-task deadline. Intermediate solver work is bounded separately and reported in the results. Every assigned task counts, including failures to publish. The local model arm gives the same task description and examples to two pinned models in each language, one generation per assignment.

The sample contains exercise families with recognizable shared structure. The measured acceptance rates apply to these bounded inputs. Differences in model training exposure to public exercise material were unmeasured. The data do not measure human time to write specifications. Freeze timestamps record materialization of the files after the tasks were selected and drafted; their interval does not measure the design effort. [Earlier nine-task block](../search/results.md) · [Earlier twelve-task block](../search-followup/results.md)

## Full-width proofs of both additional wins

After scoring, the two generated solutions that beat the largest portable minimum-cost control were checked symbolically. Z3 proved the `specialEleven` rule over every nonnegative I64 and the `sumDouble` rule for every signed input pair whose specified result fits I64. The same contracts refuted both defective starters. [Proofs and reproduction](proofs.md)

## Offline replay

Use the pinned Rust toolchain and the project's Python benchmark environment, including mypy 1.15.0. Run from the repository root. Reproduce all three native compiler builds at their exact source snapshots. The registered prior minimum-cost compiler also supplies the strict mode so later changes cannot alter that baseline. The reproduced source fingerprints should match the capture. The platform and build location can change binary hashes. [Compiler identities](compilers.json) · [Python setup](../empirical/README.md#reproduce)

```sh
mkdir -p target/search-previous target/search-minimum target/search-piecewise
git archive 8359fc6 | tar -x -C target/search-previous
git archive eaac2cd0d93591856562fc4b6cc7270fffb4fd88 | tar -x -C target/search-minimum
git archive 2f24b54e162a881167d64a2c5b7da6fa476b3bd2 | tar -x -C target/search-piecewise
cargo build --release --locked --offline --manifest-path target/search-previous/Cargo.toml
cargo build --release --locked --offline --manifest-path target/search-minimum/Cargo.toml
cargo build --release --locked --offline --manifest-path target/search-piecewise/Cargo.toml

python3 -B bench/search-confirmation/report.py bench/search-confirmation/results.jsonl
python3 -B bench/search-confirmation/confirm.py preflight target/confirm-reference-checks.json \
  --old target/search-previous/target/release/gpp
python3 -B bench/search-confirmation/confirm.py replay bench/search-confirmation/results.jsonl \
  --old target/search-previous/target/release/gpp \
  --prior target/search-minimum/target/release/gpp \
  --new target/search-piecewise/target/release/gpp
```

Preflight checks every starter and reference solution in each native language, including the withheld grid for public-passing solutions. All reference results and starter outcomes are included in [the preflight receipt](preflight.json). Replay reconstructs original prompts, consumes the exact cached replies, re-runs all native solver and control outcomes, and compares independent withheld-response digests. Timings are host observations. A recorded wall timeout can interrupt different intermediate calculations between machines.

To collect new results use a fresh archive path. The previous benchmark documents the pinned local Ollama model setup. The three collector phases can resume missing cells. The archive persists each response before it is validated. The scorer uses the real compiler's checked fill, overflow-checked Rust, and strict mypy plus Python execution. [Native adapters](../search/native.py) · [Portable cost layers](../search-followup/expanded.py)

```sh
python3 -B bench/search-confirmation/confirm.py models target/new-confirmation.jsonl \
  --old target/search-previous/target/release/gpp
python3 -B bench/search-confirmation/confirm.py portable target/new-confirmation.jsonl \
  --old target/search-previous/target/release/gpp
python3 -B bench/search-confirmation/confirm.py native target/new-confirmation.jsonl \
  --old target/search-previous/target/release/gpp \
  --prior target/search-minimum/target/release/gpp \
  --new target/search-piecewise/target/release/gpp
```

The independent oracle also matched all 33 publicly documented external example answers. [External anchor audit](external-anchors.json)
