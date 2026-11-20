# Bounded program synthesis across languages

Nine new repair tasks compare the previous shipped GPT++ compiler, the new compiler with its grammar alone, the new default guided search, and one portable compositional synthesizer with two selection policies. The portable solver renders its selected abstract expressions into GPT++, Rust and typed Python and checks them on all three native backends. A separate experiment gives two pinned local language models one fresh attempt in every language. [Results](results.md) · [Trial archive](results.jsonl) · [Frozen protocol](protocol.md) · [Advisory first-candidate protocol](secondary.md)

The four transitions update a rotary read head, a binary bit stream, a fan with two thresholds, and a moving camera. Five stateless rules test time-range intersection, the median of three sensor readings, a meeting quorum, picking parcels and checkerboard color. The public workload and independent specifications were frozen before the compiler implementation saw the tasks. The release source was frozen before running any automatic search on them. An archive of all original model requests and responses allows offline replay. [Corpus and independent pure specifications](corpus.py) · [Freeze record](freeze.json) · [Release source and compiler identities](compilers.json)

## Reproduce the head-to-head

Use the pinned Rust toolchain and the existing Python benchmark environment with mypy 1.15.0. Build both compilers at their captured git revisions with the same release profile. These commands run from the repository root. The previous checkout is created under the ignored build directory. [Python tool setup](../empirical/README.md#reproduce)

```sh
mkdir -p target/search-previous target/search-hybrid
git archive 8359fc6 | tar -x -C target/search-previous
cargo build --release --locked --offline --manifest-path target/search-previous/Cargo.toml
git archive d02eb773d6f11a64da0ebf79231199d2dc64df41 | tar -x -C target/search-hybrid
cargo build --release --locked --offline --manifest-path target/search-hybrid/Cargo.toml

python3 -B bench/search/report.py bench/search/results.jsonl
python3 -B bench/search/study.py preflight target/search-reference-checks.json \
  --old target/search-previous/target/release/gpp
python3 -B bench/search/study.py replay bench/search/results.jsonl \
  --old target/search-previous/target/release/gpp --new target/search-hybrid/target/release/gpp
```

Preflight checks the original expression and the independently written reference solution in every backend. Use a fresh output path for the preflight JSON file. Replay compares every original model prompt, public validation decision, selected expression, complete withheld-outcome digest, search-work counter and solver status. Wall times depend on the host and are excluded from replay equality. The supporting scripts use the repository's previously published scalar-expression validation boundary. Rust programs compile with overflow checking. Python uses strict mypy. GPT++ always checks supplied model expressions using its real checked-hole interface and evaluates them in the interpreter. Hidden direct cases and encoded multi-step histories run in batches on each native backend.

Fresh inference needs both model digests in the archive installed in a loopback Ollama server. Use a fresh archive path. The model run journals every reply before public validation. Rerunning a collection command can finish missing cells. The solver run requires both compiler binaries.

```sh
python3 -B bench/search/study.py models target/search-fresh.jsonl \
  --old target/search-previous/target/release/gpp
python3 -B bench/search/study.py solvers target/search-fresh.jsonl \
  --old target/search-previous/target/release/gpp --new target/search-hybrid/target/release/gpp
```

Every search uses a 30-second deadline and at most 256 fully submitted candidates. Different systems can perform substantially different work to construct those candidates. The portable synthesizer uses a public-input value table, a typed beam over ordinary integer and Boolean operators, public branch partitions and a bounded conditional join. Its public-fitting roots are rendered as native expressions. Its first-pass selector takes the first public fit. Its conservative selector abstains when fits disagree on its fixed probe grid. The grid and candidate ordering differ from the built-in compiler; this is an approximate policy control. Both selectors are applied to the identical search output. Solver score and cost should be interpreted together. [Portable grammar and bounds](engine.py)

The corpus is deliberately restricted to one editable expression. All nine named families remain in the denominator, even a family whose original expression happens to pass every public sample. The old expression and the new reference are hidden from automatic solvers apart from any information in the source contracts. Models receive the original expression and English change request in each native syntax. Only the public examples and native signatures inform the automatic controls. The two model configurations and the secondary advisory selection measure separate interventions. The freeze record measures agent elapsed time to write the shared task design and protocol. Human time was unmeasured; harness construction and inference were outside that interval.
