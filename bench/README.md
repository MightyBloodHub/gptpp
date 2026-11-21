# Benchmarks

The benchmark suite measures how much model work GPT++, typed Python, and Rust require to produce an accepted change. An accepted change passes the language checker, public examples, and withheld cases. Tokens per accepted edit includes input and output tokens from every attempt, including failures and retries. Reports include acceptance counts, timings, and paired uncertainty where available.

## Contract-gated edits

On six fresh GPT++ assignments, both compiler-only search and the opt-in workflow delivered three independently correct changes. The workflow used three trial model calls. Direct Qwen delivered one correct change in six calls. The sample leaves the 20% token-saving target unresolved at the prespecified correctness margin. [Results and costs](checked_edits/results.md) · [Replay and comparison commands](checked_edits/README.md)

## Built-in completion search

On the final eleven-exercise confirmation, the compiler’s piecewise search solved four tasks and the strongest portable minimum-cost search solved two in each language. Both portable successes were also solved by the compiler. GPT++ published three incorrect edits. Qwen solved seven exercises in each language with one model call per task. The first two automatic-search experiments are reported below. [Final results](search-confirmation/results.md) · [Proofs for both additional wins](search-confirmation/proofs.md)

In the first blind comparison, GPT++'s hybrid search and the prior release each solved one of nine fresh tasks, with one paired win and one loss. A portable expression search returned four correct changes and four incorrect changes under first-passing selection. Its stricter agreement policy abstained on every task. The archive includes every accepted and rejected outcome and separately scored model-generated changes in all three languages. [Frozen protocol](search/protocol.md) · [Nine-task results](search/results.md) · [Earlier four-task development replay](search-development/README.md)

A separate external follow-up tested minimum syntax-tree cost as a selection rule on 12 CodingBat exercises. Both the old and new compilers returned zero correct changes. The expanded portable search also solved zero. Qwen's single-shot expressions solved five in Rust, two in GPT++ and one in typed Python. [External study](search-followup/results.md) · [Expanded portable control](search-followup/expanded-results.md)

## Matched state-transition maintenance

Two models attempted four previously unseen event-driven changes in all three languages. GPT++, typed Python and Rust each accepted the same two of eight model-task assignments. The shared no-model search passed three of four families in every language. In one worked case, Qwen’s original GPT++ expression was checked against 1,088 withheld end states in both the interpreter and a compiled library called from Python. [Matched results](stateful/results.md) · [Paired comparison](stateful/paired.md) · [Runnable model completion](../examples/streak_counter/README.md)

## Symbolic verification

The symbolic verifier agreed with an independent oracle on 98 generated contracts, including 45 replayed counterexamples. GPT++, Rust with Kani, and typed Python with CrossHair each confirmed three full-width reservation cancellation properties and caught a deliberate double release. [Differential checks](proof/README.md) · [Cross-language verifier comparison](verifiers/README.md)

## Finite-contract verification and repair

On three scalar tasks, exhaustive verification rejected six of ten curated edits that passed the sparse examples. Separate contract-guided search produced a verified repair on each task. Direct execution in GPT++, Python and Rust agreed on all 373 curated program/input outcomes per language. In the supplemental model study, Qwen solved one task and StarCoder2 solved none. [Finite-domain results](contracts/results.md) · [Model results](contracts/model-results.md) · [Reproduction](contracts/README.md)

## Earlier language and workflow measurements

A matched expression-generation study gave two models equivalent task information and one public-test retry in GPT++, typed Python and Rust. It covers three historical tasks and three new scalar contracts. The new-task failures identified useful expressions that GPT++ could not yet represent. After adding typed integer operations and explicit Boolean conversion, replaying the same replies recovered all three Qwen arithmetic repairs. The report records the adaptation and charges every original token. [New contracts](expression/results/fresh-agent.md) · [Historical tasks](expression/results/agent.md) · [Language-extension replay](expression/results/compat.md)

A compiler session now checks and executes many candidate edits from one source snapshot. The latency study compares complete commands before and after that implementation change and requires identical menus and questions. A separate native execution study compares correct scalar programs in the three languages. [Compiler latency](expression/results/probe.md) · [Runtime and memory](runtime/results.md)

## Example-filtered repair

The repair study tests a division of work in which the compiler traces supplied calls, a tool searches bounded expressions, and a local model chooses among edits that satisfy public examples. Its independent scorer tests both the model choice and a deterministic first choice. [Repair results](expression/results/repair.md) · [Study protocol](expression/repair-protocol.md)

## Earlier expression-edit study

The v9 study compares checked expression edits with whole-function edits in GPT++, typed Python and Rust. It measures the cost of finding the edit inside a known function and separately measures editing when the caller supplies a location. Each task extracts one historical fix and two consumer paths from Redis, FastLED or Go. A follow-up tests numbered syntax nodes with schema-constrained output. [Expression study and conclusions](expression/README.md) · [Upstream source audit](expression/sources.md)

## Earlier maintenance results

The eight-task policy study found lower token costs for Qwen's native GPT++ body edits under the caller-retry workflow. On the three upstream fixes, the cheapest observed GPT++ and typed Python workflows each accepted one different fix and cost 1,120 and 1,121 tokens per accepted edit respectively. The upstream fixtures extract scalar code from Linux, Moment.js, and Godot, keep identifiable upstream consumers, and supply the target function. [Maintenance results](policy/README.md) · [Upstream sources and fixture boundaries](policy/upstream-sources.md) · [Qualification criteria](../docs/design.md#197-evidence-for-comparative-claims)

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
| [Matched expression generation](expression/agent-protocol.md) | How do caller context, observations and one retry compare across languages? | [Historical report](expression/results/agent.md) | [JSONL](expression/results/agent.jsonl) |
| [New arithmetic contracts](expression/agent-fresh-protocol.md) | Which edits transfer to three new scalar contracts? | [Report](expression/results/fresh-agent.md) | [JSONL](expression/results/fresh-agent.jsonl) |
| [Native scalar operations](expression/compat-protocol.md) | Which saved model proposals become correct with the added operations? | [Report](expression/results/compat.md) | [JSONL](expression/results/compat.jsonl) |
| [Matched state-transition changes](stateful/protocol.md) | What changes with the language under the same typed edit interface and sequence contracts? | [Report](stateful/results.md) | [JSONL](stateful/results.jsonl) |
| [Finite contracts](contracts/protocol.md) | Which example-passing edits survive every declared input? | [Report](contracts/results.md) | [JSONL](contracts/results.jsonl) |
| [Contract-guided model edits](contracts/model-protocol.md) | Can local models generate a checked edit with at most one counterexample retry? | [Report](contracts/model-results.md) | [JSONL](contracts/model-results.jsonl) |
| [Compiler session latency](expression/probe-protocol.md) | How much work does batching remove with identical outcomes? | [Report](expression/results/probe.md) | [JSONL](expression/results/probe.jsonl) |
| [Scalar runtime](runtime/README.md) | How do correct compiled and interpreted programs use time and memory? | [Report](runtime/results.md) | [JSONL](runtime/results.jsonl) |
| [Example-filtered repair](expression/repair-protocol.md) | What changes when the model chooses from tested replacement expressions? | [Report](expression/results/repair.md) | [JSONL](expression/results/repair.jsonl) |
| [Choosing a distinguishing input](expression/distinguish-protocol.md) | How many new answers from a specification oracle isolate a patch? | [Report](expression/results/distinguish.md) | [JSONL](expression/results/distinguish.jsonl) |

## Reproduce the results

Run commands from the repository root. Report generation reads archived data with Python and requires no model. Behavioral replay uses the recorded compiler, Python environment, and macOS evaluation sandbox. New inference also requires Ollama and the model digests named in the study archive. The study guides specify the exact environment and commands. [Environment setup](empirical/README.md#reproduce) · [Earlier iterations](iterate/README.md#reproduce) · [Expression-study setup](expression/README.md#reproduce)

The v1 report and raw trials describe an earlier compiler revision. Its manifest records five source hashes from before this Git snapshot. The saved report can be regenerated from the archive. Running the current compiler on those cases is a follow-up comparison. [Scalar pilot](empirical/README.md) · [Follow-up replay](iterate/replay_v1.py)

Regenerate the expression-study tables without inference.

```sh
python3 -B bench/expression/repair_study.py --report bench/expression/results/repair.jsonl
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
