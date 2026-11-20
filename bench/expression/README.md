# Expression edits on historical maintenance tasks

The compiler can replace a single expression while keeping its callers and surrounding code intact. In this study, both models struggled to decide **which expression to change and what value it should compute**. Giving a model the correct site produced one GPT++ repair. Charging the model for finding the site produced zero accepted GPT++ repairs.

The main experiment used three historical changes from Redis, FastLED and Go, two caller paths per change, three languages and two local models. Each language received the same public examples, edit scope and retry rule. The target function was supplied. There were **72 assigned trials and 92 model calls**. A follow-up generated **18 more calls** on those same tasks. [Frozen protocol](protocol.md) · [Upstream revisions, test domains and callers](sources.md)

## What passed

| Workflow | GPT++ | Typed Python | Rust |
|---|---:|---:|---:|
| Model copies the old expression, then fills it | 0/6 | 0/6 | 0/6 |
| Model gives the old and new expression together | 0/6 | 0/6 | 0/6 |
| Editor supplies the site, one attempt | 1/6 | 0/6 | 1/6 |
| Whole-body edit with a caller-triggered retry | 0/6 | 0/6 | 1/6 |
| Follow-up with numbered expressions, one call | 0/6 | 0/6 | 0/6 |

Each cell covers three tasks on each of two models. The successful known-site edits both repaired Redis on StarCoder2. The successful whole-body edit repaired Go on Qwen's retry. Public caller failures triggered 19 retries across the original study and recovered this one change. The first prompts contained the target function and public assertions. Caller implementation excerpts appeared only on eligible retries. [Per-model results and uncertainty](results/expression.md) · [Prompts and completions](results/expression.jsonl)

### Distance to the 20% goal

The prespecified Qwen comparison counted the cost of selecting and editing a site. GPT++, typed Python and Rust each finished with **0/3** accepted changes. A cost per accepted edit and its percentage saving are therefore undefined.

The direct numerical comparison was the secondary, **known-site StarCoder2** condition. GPT++ used **908** tokens per accepted change, Rust **897**, and typed Python had zero accepts. Both successful edits fixed the same Redis call paths. The GPT++ point estimate was **1.23% more expensive than Rust**, leaving a gap of **21.23 percentage points** to the 20% savings goal. Reaching it would have required at most **717.6** tokens per accepted edit. The paired interval for the cost ratio spans zero to infinity because many resamples have zero successes. This is a development result on three scalar extracts. [Paired comparisons](results/expression.md)

## What changed after the first run

Free-text selection produced one valid expression across 18 standalone locator calls. None of the 18 combined old/new diff responses satisfied the required format and uniquely selected a site. In the known-site GPT++ arm, all three Qwen first responses continued beyond the expression into a semicolon. The model often attempted to complete the surrounding program.

We added an experimental one-call editor that lists the actual syntax nodes, assigns a distinct ID to each occurrence, and constrains the reply to an ID and a replacement string. GPT++, typed Python and Rust each received the same interface. This follow-up ran on the original tasks after the failures were inspected. It measures the combined effect of the catalog, JSON decoding and ordinary prompt transport. [CLI usage](../../tools/README.md#pick-a-numbered-expression) · [Follow-up protocol](catalog-protocol.md)

All **18/18** responses identified a listed site. **0/18** passed both public and withheld tests. For example, Qwen's Python Redis change passed all public cases but mapped a valid maximum timestamp to zero. Its GPT++ Go change tried to multiply a Boolean by an integer. StarCoder2's three GPT++ replacements all introduced recursive call paths that exhausted the interpreter's budget. The full catalog also cost tokens. On Qwen, the three GPT++ follow-up calls used 1,507 tokens in total, compared with 884 for the original three standalone selections that failed before the edit call. [Catalog results](results/catalog.md) · [All structured responses](results/catalog.jsonl)

## Verification

- The 9 public and 43 withheld examples exercise both changed and preserved behavior. All three reference languages passed all 52 cases, and all nine hand-authored expression patches passed the same checks after applying through the editing adapters. Independent execution of the pinned upstream calculations matched the fixture translations in 288,140 comparisons. [Fixture boundaries](sources.md) · [Upstream verifier](verify_upstream.py)
- The two frozen studies archive exact requests, completions, sampling settings and usage. Behavioral replay reconstructs the edits and reruns the checks. For Rust panic diagnostics it compares all text except the process-specific thread number, then restores the recorded number when reconstructing a retry prompt. Both patch hashes and recorded model prompts must still match. [Replay program](replay.py)
- A separate product replay exercised all 18 original GPT++ expression trials through the real proposal CLI. All 19 generated requests matched the archive byte-for-byte, including the caller retry. The successful patch matched its hash and passed withheld cases. A further live StarCoder2 run produced the same Redis fix, passed the public cases and built a native program whose caller returned the expected 16,776,225. [CLI parity checker](replay_product.py)

## Reproduce

Run the following commands from the repository root. Regenerating reports only requires Python 3.10 or newer.

```sh
python3 -B bench/expression/report_expression.py bench/expression/results/expression.jsonl
python3 -B bench/expression/catalog_study.py --report bench/expression/results/catalog.jsonl
```

For behavioral replay, use the pinned macOS, Rust and Python setup from the earlier maintenance studies. The standalone Rust syntax helper uses a locked Cargo dependency tree. On a machine with an empty Cargo cache, fetch it once. Archived replay checks executable and source hashes. Rust debug builds can vary with checkout path, toolchain and platform. The saved reports can be regenerated independently of those binaries. [Baseline environment](../empirical/README.md#reproduce)

```sh
cargo build --locked --offline
cargo fetch --locked --manifest-path bench/expression/rust_syntax/Cargo.toml
cargo build --locked --offline --manifest-path bench/expression/rust_syntax/Cargo.toml --target-dir target/expr-rust-syntax
target/empirical-venv/bin/python -B bench/expression/replay.py
target/empirical-venv/bin/python -B bench/expression/replay_product.py bench/expression/results/expression.jsonl
```

To reproduce the native upstream comparison, run `python3 -B bench/expression/verify_upstream.py` with a C compiler and Go installed. It fetches nine source files by pinned revision and checks each content hash. Add `--offline` to use the verified cache.

For new generations, use local Ollama with the two archived model digests. The follow-up uses the checked-in original archive as its comparator. Keep new runs at fresh paths.

```sh
target/empirical-venv/bin/python -B bench/expression/run_expression.py target/expression-new.jsonl
target/empirical-venv/bin/python -B bench/expression/catalog_study.py target/catalog-new.jsonl
```
