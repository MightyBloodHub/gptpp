# GPT++ maintenance experiments

The ordered rule language can express every change in the eight-task policy corpus. Neither model authored a rule patch that passed all tests. On Qwen2.5-Coder 7B, replacing the native GPT++ body worked best. Five of eight edits passed, and all five succeeded on the first call. The same whole-body workflow in typed Python accepted three edits and Rust accepted five. [Implementation and usage](../../tools/README.md) · [Eight independently written passing policies](witnesses.py)

## Eight fresh policy tasks

Each task has a public change description, a known target and two unchanged callers. The 24 public and 104 withheld examples include required changes and preserved behavior. Three independently checked language references passed all 384 judgments. Two models tried seven workflows each, for 112 assigned trials and 164 real calls. Only a public caller failure could reveal caller source for a single retry. All 21 accepted edits succeeded on their first attempt. The 52 retries in this study added zero accepts. [Protocol](protocol.md) · [Raw prompts, completions and usage](results/policy.jsonl) · [Complete tables with intervals](results/policy.md)

| Qwen workflow | Accepted | Total tokens including failures | Tokens per accepted edit |
|---|---:|---:|---:|
| Native GPT++ whole body | 5/8 | 2,501 | 500.20 |
| Typed Python whole body | 3/8 | 3,175 | 1,058.33 |
| Rust whole body | 5/8 | 3,917 | 783.40 |
| Native GPT++ insert before existing body | 2/8 | 4,295 | 2,147.50 |
| Typed Python insert before existing body | 2/8 | 3,386 | 1,693.00 |
| Rust insert before existing body | 2/8 | 4,376 | 2,188.00 |
| GPT++ ordered rules | 0/8 | 6,145 | Undefined |

The registered primary comparison was ordered rules versus typed Python insertion. With zero successful rule edits, that hypothesis failed. In the exploratory native whole-body comparison, GPT++ used 52.7% fewer tokens per success than Python and 36.2% fewer than Rust. Those point estimates beat the 20% target by 32.7 and 16.2 percentage points. The paired 95% cost-ratio intervals were 0.075–1.112 against Python and 0.239–1.474 against Rust. Both exceed the required 0.80 upper bound.

Removing retries changes the Qwen comparison. The same 5 GPT++, 3 Python and 5 Rust edits passed on their first attempt. First-call costs per accepted edit were 500.20 for GPT++, 762.00 for Python and 465.00 for Rust. GPT++ used 34.4% fewer tokens than one-shot Python and 7.6% more than one-shot Rust. Three unsuccessful Rust retries account for its reversal in the adaptive comparison. This distinction matters when attributing the apparent advantage to language syntax.

StarCoder2 3B accepted one native GPT++ insertion at 5,728 tokens per success and one Python whole-body edit at 4,481. All other arms had zero accepts. GPT++ cost 27.8% more than Python here, a 47.8-point shortfall against the goal. The pinned Ollama installation and the published StarCoder2 tokenizer split some text differently. All comparisons use each installed model's reported token counts. [Offline verifier](verify_policy.py)

The failure modes differed. Six Qwen rule patches returned wrong results. Two used constructs outside the checked scalar expression language. All eight StarCoder2 rule patches failed checking. The targeted corpus makes explicit decision rules plausible, yet both models found the familiar native body authoring task easier on at least one arm. All three languages received matching native fallback and whole-body controls. [Prior failure diagnosis](diagnosis.md) · [Scoped rule compiler and semantics](../../tools/policy.md)

## Historical upstream transfer

The three changes were frozen independently of the development results. They cover signed nearest-integer rounding in Linux, February in astronomical year zero in Moment.js, and rectangle borders in Godot. Each extraction has two identifiable upstream consumers. The three translated references passed 183 judgments. The bounded scalar targets agreed with the actual pre-fix and post-fix upstream code on 6,396 additional inputs per revision. The full projects and their I/O were outside this experiment. The selected workflows were frozen before upstream inference. [Commit and caller provenance](upstream-sources.md) · [Transfer protocol](transfer-protocol.md) · [Underlying source verification](verify_upstream_sources.py)

| Model and workflow | Accepted | Tokens across three tasks | Tokens per accepted edit |
|---|---:|---:|---:|
| Qwen, selected native GPT++ body | 1/3 | 2,441 | 2,441 |
| Qwen, selected typed Python body | 0/3 | 2,114 | Undefined |
| Qwen, selected Rust body | 0/3 | 2,704 | Undefined |
| Qwen, GPT++ ordered rules | 1/3 | 1,120 | 1,120 |
| Qwen, typed Python insertion | 1/3 | 1,121 | 1,121 |
| Qwen, native GPT++ insertion | 1/3 | 1,592 | 1,592 |
| StarCoder2, all seven workflows | 0/3 each | See full table | Undefined |

Native GPT++ repaired Linux rounding. The ordered rules repaired Godot's border condition. The typed Python insertion repaired the Moment.js calendar case. No Rust arm produced a passing change. Across 42 trials and 66 calls, all four successes came on the first try. The selected ratios could not be estimated on either model. In the **post-hoc comparison of the lowest observed costs**, GPT++ saved one token per success against typed Python, or **0.09%**. The 20% target was **896.80**. GPT++ missed it by **223.20 tokens per success** or **19.91 percentage points**. The two edits solved different tasks. [All arms, failures, intervals and timing](results/transfer.md) · [Raw trials](results/transfer.jsonl)

Two failed native outputs show what a smaller edit could buy. The Moment.js patch rewrote the month-length calculation while retaining the unwanted 1900-year offset. The Godot patch kept an inclusive comparison at a touching border. Both cases suggest testing replacement of an existing expression or comparison with a compiler-checked edit, while keeping the surrounding native body intact. These three projects are now development examples for that hypothesis. Further qualification needs unseen projects and equal edit granularity in all three languages.

## Product verification

The compact maintenance preset exposes the selected Qwen whole-body workflow. A protected insertion is available with `--prepend`. The product CLI reproduced all 22 selected native GPT++ trial outcomes across the two studies when supplied their archived completions. Fourteen of 31 prompt/suffix pairs were byte-identical to the benchmark inputs. The compiler's normal formatting of the source accounts for the difference in the others. Fresh generations can vary with formatting. [Product parity report](product-parity.md) · [Proposal CLI](../../tools/README.md)

The GPT++ caller analyzer handles cases where the unchanged caller's checked computation determines a single target output at one input. On the previous two studies it extracted four distinct required outputs from 12 distinct failing caller assertions. All four matched the independent references. All 24 upstream retries fell back to caller excerpts. [Historical coverage audit](audit_obligations.md) · [Derivation rules](../../tools/caller_obligation.md)

### Does a smaller retry fix the edit?

The paired ablation made 15 new model calls on **every** eligible v7 retry across both models. Each retry kept the first failed completion, public diagnostic, model settings and protected suffix. It replaced the caller excerpts with a single target result required by the public caller assertion. The 15 cells involved three distinct assertions. The exact result reduced Qwen's retry tokens from 4,491 to 3,402 (24.2%) and StarCoder2’s from 4,006 to 2,957 (26.2%). Neither variant recovered any of these 15 edits. Across all 56 development assignments per model, the substitutions saved 3.9% and 2.9% of tokens respectively. Shorter feedback is measurable, while the 20% goal concerns the entire cost of an accepted edit. [Paired new generations](results/retry-obligations.md) · [Raw alternate retries](results/retry-obligations.jsonl) · [Eligibility and protocol](retry-obligations-protocol.md)

Independent replay reproduced all 164 development patch decisions, 141 public evaluations and 24 withheld evaluations. The transfer archive replay reproduced all 66 completions, and the matched retry archive replay reproduced all 15. Independent retokenization matched the installed model’s input counts for each study. An end-to-end Qwen run on the documented maintenance entry point produced a revision-checked patch that passed its target and caller examples and compiled to a native executable. [Transfer verifier](verify_transfer.py) · [Matched retry evaluation](retry_obligations.py)

## Reproduce

Use the pinned local models and evaluation environment from the [earlier maintenance study](../maintenance/README.md). Run from the repository root. The corpus, runner, compiler, protocol and model digests are recorded in each raw archive.

```sh
target/empirical-venv/bin/python -B bench/policy/witnesses.py
target/empirical-venv/bin/python -B bench/policy/run_policy.py target/policy-new.jsonl
python3 -B bench/policy/report_policy.py bench/policy/results/policy.jsonl
target/empirical-venv/bin/python -B bench/policy/verify_policy.py --replay bench/policy/results/policy.jsonl
rustc --edition=2024 -O tools/caller_obligation.rs -o target/caller-obligation
target/empirical-venv/bin/python -B bench/policy/verify_upstream_sources.py --cache target/upstream-oracles
target/empirical-venv/bin/python -B bench/policy/run_transfer.py target/transfer-new.jsonl
target/empirical-venv/bin/python -B bench/policy/run_transfer.py --replay bench/policy/results/transfer.jsonl
```
