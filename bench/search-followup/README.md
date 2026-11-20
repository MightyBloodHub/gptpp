# Minimum-cost native completion and portable controls

Twelve externally specified scalar exercises compare GPT++'s original grammar, strict guided search, and its explicit minimum-cost selector. Public examples, native signatures, submitted-candidate limits, time limits and withheld cases were fixed in advance. A typed compositional solver supplies portable candidates that are independently compiled and checked in GPT++, Rust and typed Python. Two local models also attempted every task once in every language. The exercised rules contain no custom libraries or multi-file edits. [Results](results.md) · [Raw trials](results.jsonl) · [Protocol](protocol.md) · [Sources and attribution](sources.md) · [Independent oracles](corpus.py)

The tasks are finite-domain adaptations of twelve CodingBat exercises. Their original authors specified the rules before this compiler existed. The task-authoring agent picked the block and froze the public/withheld split before seeing the second implementation. Each task exposes 24 labeled examples. The other 22,675 finite-grid tuples are checked using independent oracles. Public availability of the exercises makes previous model exposure possible. These 12 scalar tasks form a different block from the [first nine new tasks](../search/README.md).

The primary portable control applies three selectors to the same bounded search output. A separately preregistered secondary control increases the portable intermediate work budget to match the sum of three native design bounds, with the same 256-root and 30-second limits. Every issued native model reply and every published portable candidate was checked in its actual language. The portable search policies and the models have access only to public inputs at selection. Single-call local generation also receives the same-English task description and adapter-specific syntax instructions. Runtime measurements are one-host observations. [Secondary protocol](expanded-protocol.md) · [Secondary results](expanded-results.md)

## Reproduction

Use the repository's pinned Rust compiler and Python benchmark environment, including mypy 1.15.0. Run from the repository root. The two optimized builds below match the captured compiler source revisions. Compiler binary hashes depend on the build location and toolchain. [Python setup](../empirical/README.md#reproduce) · [Compiler fingerprints](compilers.json) · [Task freeze](freeze.json)

```sh
mkdir -p target/search-previous target/search-minimum
git archive 8359fc6 | tar -x -C target/search-previous
git archive eaac2cd0d93591856562fc4b6cc7270fffb4fd88 | tar -x -C target/search-minimum
cargo build --release --locked --offline --manifest-path target/search-previous/Cargo.toml
cargo build --release --locked --offline --manifest-path target/search-minimum/Cargo.toml

python3 -B bench/search-followup/report.py bench/search-followup/results.jsonl
python3 -B bench/search-followup/followup.py preflight target/search-followup-preflight.json \
  --old target/search-previous/target/release/gpp
python3 -B bench/search-followup/followup.py replay bench/search-followup/results.jsonl \
  --old target/search-previous/target/release/gpp --new target/search-minimum/target/release/gpp
python3 -B bench/search-followup/expanded.py replay bench/search-followup/expanded.jsonl \
  --old target/search-previous/target/release/gpp
```

The primary replay recomputes every original prompt and checks the saved response, the search results, the decisions to publish, public failures and the independent withheld-output digests. The supplemental replay reruns the larger portable search, its three selectors and every checked native rendering. Neither replay calls a model. Preflight checks every starter and reference against the public/withheld gates. Use a fresh output file for preflight.

For new measurements, use a fresh archive path and two local Ollama models matching the digests recorded in the archive. The earlier matched study documents the base inference environment. The primary collector writes each original model response before attempting native validation. Separate commands can resume completed cells with matching fingerprints. The expanded search uses a fresh JSONL file. [Pinned model workflow](../stateful/README.md#reproduce)

```sh
python3 -B bench/search-followup/followup.py models target/followup-fresh.jsonl \
  --old target/search-previous/target/release/gpp
python3 -B bench/search-followup/followup.py solvers target/followup-fresh.jsonl \
  --old target/search-previous/target/release/gpp --new target/search-minimum/target/release/gpp
python3 -B bench/search-followup/expanded.py collect target/followup-expanded.jsonl \
  --old target/search-previous/target/release/gpp
```

The expanded collector initially used the language work-directory name for its temporary compiler binary. That invocation stopped before recording a scored row. Renaming the temporary binary allowed the frozen solver and tasks to run. The archive includes every completed trial. [Setup record](expanded-setup.json) · [Offline replay receipt](replay.json)
