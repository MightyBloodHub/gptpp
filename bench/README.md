# Benchmarks

The benchmark suite measures how much model work GPT++, typed Python, and Rust require to produce an accepted change. An accepted change passes the language checker, public examples, and withheld cases. Tokens per accepted edit includes input and output tokens from every attempt, including failures and retries. Reports include acceptance counts, timings, and paired uncertainty where available.

## Start with the expression-edit study

The latest study compares checked expression edits with whole-function edits in GPT++, typed Python and Rust. It measures the cost of finding the edit inside a known function and separately measures editing when the caller supplies a location. Each task extracts one historical fix and two consumer paths from Redis, FastLED or Go. A follow-up tests numbered syntax nodes with schema-constrained output. [Expression study and conclusions](expression/README.md) · [Upstream source audit](expression/sources.md)

## Earlier maintenance results

The eight-task policy study found lower token costs for Qwen's native GPT++ body edits under the caller-retry workflow. On the three upstream fixes, the cheapest observed GPT++ and typed Python workflows each accepted one different fix and cost 1,120 and 1,121 tokens per accepted edit respectively. The upstream fixtures extract scalar code from Linux, Moment.js, and Godot, keep identifiable upstream consumers, and supply the target function. The 20% efficiency goal remains open. [Maintenance results](policy/README.md) · [Upstream sources and fixture boundaries](policy/upstream-sources.md) · [Qualification criteria](../docs/design.md#197-proposed-gono-go-thresholds)

## Study index

| Study | Question | Results | Raw records |
|---|---|---|---|
| [Calibration](pilot/README.md) | Do the three languages agree on a reviewed shipping-fee repair? | [Expected values](pilot/cases.tsv) | — |
| [Scalar pilot (v1)](empirical/README.md) | How do two models perform on scalar synthesis and maintenance? | [Report](empirical/results/2026-11-19.md) | [JSONL](empirical/results/2026-11-19.jsonl) |
| [Scoped edits (v2)](iterate/protocol.md) | How does completing a fragment compare with rewriting the function? | [Report](iterate/results/paired.md) | [JSONL](iterate/results/paired.jsonl) |
| [Infill (v3)](iterate/infill-protocol.md) | What changes when the model fills a source gap? | [Report](iterate/results/infill.md) | [JSONL](iterate/results/infill.jsonl) |
| [Boundary stops (v4)](iterate/boundary-protocol.md) | How does stopping generation at the edit boundary affect cost and acceptance? | [Report](iterate/results/boundary.md) | [JSONL](iterate/results/boundary.jsonl) |
| [Multi-caller maintenance (v5)](maintenance/README.md) | What does caller context contribute to repairs in shared functions? | [Report](maintenance/results/maintenance.md) | [JSONL](maintenance/results/maintenance.jsonl) |
| [Adaptive caller context (v6)](adaptive/README.md) | What changes when a failed caller test triggers context? | [Report](adaptive/results/adaptive.md) | [JSONL](adaptive/results/adaptive.jsonl) |
| [Policy maintenance (v7)](policy/protocol.md) | How do native body edits, protected insertions, and ordered rules compare? | [Report](policy/results/policy.md) | [JSONL](policy/results/policy.jsonl) |
| [Upstream transfer (v8)](policy/transfer-protocol.md) | How do the selected workflows perform on historical fixes? | [Report](policy/results/transfer.md) | [JSONL](policy/results/transfer.jsonl) |
| [Caller-retry comparison](policy/retry-obligations-protocol.md) | What happens when a retry gets a derived target result in place of caller excerpts? | [Report](policy/results/retry-obligations.md) | [JSONL](policy/results/retry-obligations.jsonl) |
| [Expression edits (v9)](expression/protocol.md) | Can a model locate and replace one expression more cheaply? | [Report](expression/results/expression.md) | [JSONL](expression/results/expression.jsonl) |
| [Compiler-listed selections](expression/catalog-protocol.md) | What changes when the decoder requires an existing site ID? | [Report](expression/results/catalog.md) | [JSONL](expression/results/catalog.jsonl) |

## Reproduce the results

Run commands from the repository root. Report generation reads archived data with Python and requires no model. Behavioral replay uses the recorded compiler, Python environment, and macOS evaluation sandbox. New inference also requires Ollama and the model digests named in the study archive. The study guides specify the exact environment and commands. [Environment setup](empirical/README.md#reproduce) · [Earlier iterations](iterate/README.md#reproduce) · [Expression-study setup](expression/README.md#reproduce)

The v1 report and raw trials describe an earlier compiler revision. Its manifest records five source hashes from before this Git snapshot. The saved report can be regenerated from the archive. Running the current compiler on those cases is a follow-up comparison. [Scalar pilot](empirical/README.md) · [Follow-up replay](iterate/replay_v1.py)

Regenerate the expression-study tables without inference.

```sh
python3 -B bench/expression/report_expression.py bench/expression/results/expression.jsonl
python3 -B bench/expression/catalog_study.py --report bench/expression/results/catalog.jsonl
```

Regenerate the earlier policy and transfer reports from their archives.

```sh
python3 -B bench/policy/report_policy.py bench/policy/results/policy.jsonl
python3 -B bench/policy/report_policy.py bench/policy/results/transfer.jsonl
```

For behavioral replay of v7 and v8, build the archived GPT++ compiler from revision `4c82a66` in a separate checkout and use its pinned evaluation environment. The checked expression editor changes the compiler fingerprint. [Expression-study replay commands](expression/README.md#reproduce)

```sh
target/empirical-venv/bin/python -B bench/policy/verify_policy.py --replay bench/policy/results/policy.jsonl
rustc --edition=2024 -O tools/caller_obligation.rs -o target/caller-obligation
target/empirical-venv/bin/python -B bench/policy/run_transfer.py --replay bench/policy/results/transfer.jsonl
target/empirical-venv/bin/python -B bench/policy/retry_obligations.py --replay
```

For a new run, write to a fresh path under `target/` and keep the published archive available for replay. The development corpora and archived outputs are public and should be excluded from future qualification sets.
