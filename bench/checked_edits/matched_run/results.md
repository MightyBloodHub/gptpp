# Matched-helper sensitivity

These are the pilot’s six families rechecked with the advertised `abs` helper available in the GPT++ sketch. Each model request reused its primary receipt only on an exact request match within the same assignment. Changed requests used live Qwen. This supplemental comparison cannot qualify the workflow on fresh families.

| Stage | Replayed calls | Live calls | Attributed input/output | Physical input/output | Attributed model s | Physical model s |
|---|---:|---:|---:|---:|---:|---:|
| Preparation | 6 | 0 | 1,468/84 | 0/0 | 13.87 | 0.00 |
| Trial | 89 | 0 | 21,322/1,932 | 0/0 | 143.35 | 0.00 |
| Total | 95 | 0 | 22,790/2,016 | 0/0 | 157.22 | 0.00 |

The outcomes table charges the original measured input, output and model time for reused replies. Public compiler work and sealed scoring ran again. Each `primary_line` points to the reused prompt and reply in the primary ledger whose SHA-256 is in this run’s manifest.

## Paired outcomes

GPT++’s workflow produced 3/6 independently correct edits in 3 model calls. One-call direct Qwen produced 1/6 in 6 calls. Including the shared contract audit, tokens per correct edit had a workflow/direct ratio of 0.29.

## Acceptance and cost

Each row covers six supplemental assignments. First C/P counts independently correct edits and publications on the first pass. Final C/W/A counts correct publications, wrong publications and abstentions. Trial tokens/correct charges all attempts and any metered answer-source tokens, including failures. All tokens/correct also charges the six preparation audit requests to each standalone method. Input, output, calls, model seconds and tool seconds in this table count trial work. Tool time includes non-model trial overhead. Charged seconds add trial wall time, per-trial scoring and the full shared preparation and calibration cost to each standalone method.

| Language | Method | First C/P | Final C/W/A | Final published | Calls | Input | Output | Trial tokens/correct | All tokens/correct | Model s | Tool s | Trial wall s | Score s | Charged s |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GPT++ | Direct | 1/1 | 1/0/5 | 1 | 6 | 1,312 | 98 | 1410.00 | 2962.00 | 9.47 | 0.17 | 9.64 | 0.02 | 227.42 |
| GPT++ | Direct + blind retry | 1/1 | 1/0/5 | 1 | 11 | 2,569 | 186 | 2755.00 | 4307.00 | 13.95 | 0.28 | 14.23 | 0.02 | 232.01 |
| GPT++ | Direct + witness | 1/1 | 1/0/5 | 1 | 11 | 2,667 | 177 | 2844.00 | 4396.00 | 13.56 | 0.32 | 13.89 | 0.02 | 231.66 |
| GPT++ | Compiler only | 3/3 | 3/0/3 | 3 | 0 | 0 | 0 | 0.00 | 517.33 | 0.00 | 0.63 | 0.63 | 0.06 | 218.45 |
| GPT++ | Workflow | 3/3 | 3/0/3 | 3 | 3 | 943 | 75 | 339.33 | 856.67 | 6.84 | 0.73 | 7.57 | 0.06 | 225.39 |
| Typed Python | Direct | 2/2 | 2/0/4 | 2 | 6 | 1,243 | 96 | 669.50 | 1445.50 | 8.67 | 4.35 | 13.01 | 1.71 | 232.48 |
| Typed Python | Direct + blind retry | 2/2 | 2/0/4 | 2 | 10 | 2,206 | 155 | 1180.50 | 1956.50 | 12.37 | 7.05 | 19.42 | 1.66 | 238.84 |
| Typed Python | Direct + witness | 2/2 | 3/0/3 | 3 | 10 | 2,311 | 158 | 823.00 | 1340.33 | 12.54 | 6.88 | 19.41 | 2.51 | 239.68 |
| Typed Python | Compiler only | 3/3 | 3/0/3 | 3 | 0 | 0 | 0 | 0.00 | 517.33 | 0.00 | 10.46 | 10.46 | 2.55 | 230.77 |
| Typed Python | Workflow | 3/3 | 4/0/2 | 4 | 3 | 908 | 50 | 239.50 | 627.50 | 5.94 | 13.07 | 19.01 | 3.42 | 240.19 |
| Rust | Direct | 2/2 | 2/0/4 | 2 | 6 | 1,303 | 187 | 745.00 | 1521.00 | 12.55 | 2.77 | 15.32 | 0.80 | 233.87 |
| Rust | Direct + blind retry | 2/2 | 2/0/4 | 2 | 10 | 2,397 | 356 | 1376.50 | 2152.50 | 21.15 | 4.99 | 26.15 | 0.92 | 244.82 |
| Rust | Direct + witness | 2/2 | 2/0/4 | 2 | 10 | 2,524 | 320 | 1422.00 | 2198.00 | 19.42 | 5.23 | 24.65 | 0.79 | 243.19 |
| Rust | Compiler only | 3/3 | 3/0/3 | 3 | 0 | 0 | 0 | 0.00 | 517.33 | 0.00 | 6.61 | 6.61 | 1.23 | 225.59 |
| Rust | Workflow | 3/3 | 4/0/2 | 4 | 3 | 939 | 74 | 253.25 | 641.25 | 6.89 | 9.20 | 16.10 | 1.75 | 235.60 |

Preparing 6 acceptance properties and 24 example labels took 167.0 elapsed seconds. The six shared Qwen mutation-audit calls added 1,468 input tokens, 84 output tokens and 13.87 model seconds (14.08 s including checks). Public calibration took 19.82 s and independent scorer calibration took 16.86 s. Human minutes and development-author tokens were unmetered. The observed cost ratio remains within target for every equal, nonnegative preparation-token charge.

Across 90 assignments there were 125 candidate checks ending in rejection or abstention, 35 model repair attempts and 0 distinguishing questions. Authorized sources received 0 queries and supplied 0 extra labels. Counting shared costs once gives 451.38 charged seconds for the study. [Decisions, prompts and receipts](decisions.jsonl) · [Closed independent scores](scores.json)

## Paired GPT++ decisions

Helped and hurt name the tasks on which only one method was independently correct. Ties are both correct / neither correct. Calls saved subtracts the left method’s calls from the comparator’s. The primary comparison is workflow versus one-call direct Qwen. The matched retry controls isolate the additional public counterexample in the retry prompt.

| Left method vs comparator | Helped | Hurt | Ties | Calls saved | Correctness Δ pp [95%] | Cost ratio [95%] | Undefined resamples |
|---|---|---|---:|---:|---:|---:|---:|
| Workflow vs Direct | mirror_carriage, proof_sheet | — | 1/3 | 3 | +33.3 [-48.8, 81.6] | 0.29 [0.00, ∞] | 33.5% |
| Workflow vs Direct + blind retry | mirror_carriage, proof_sheet | — | 1/3 | 8 | +33.3 [-48.8, 81.6] | 0.20 [0.00, ∞] | 33.5% |
| Workflow vs Direct + witness | mirror_carriage, proof_sheet | — | 1/3 | 8 | +33.3 [-48.8, 81.6] | 0.19 [0.00, ∞] | 33.5% |
| Workflow vs Compiler only | — | — | 3/3 | -3 | +0.0 [-51.8, 51.8] | 1.66 [1.00, 2.11] | 1.6% |
| Direct + witness vs Direct + blind retry | — | — | 1/5 | 0 | +0.0 [-51.8, 51.8] | 1.02 [0.00, ∞] | 33.5% |

The proposed engineering target requires a 95% lower correctness-difference bound of at least −2 percentage points and a 95% upper tokens-per-correct ratio of at most 0.80. The paired correctness interval subtracts simultaneous 97.5% exact binomial intervals for the win and loss probabilities (Bonferroni joint coverage ≥95%). The descriptive cost interval uses the 2.5th and 97.5th percentiles of all 46,656 ordered paired six-family bootstrap samples, charging each sampled family’s audit tokens to both methods. A zero success count or zero reference cost makes the cost ratio undefined. Undefined resamples widen the percentile bounds using their full possible range.

Six task families and one model leave the correctness margin unresolved. These measurements are inconclusive for the engineering target and for a language-wide advantage. Keep the workflow opt-in.

## Matched assignments by language

Each cell gives final outcome/model calls. C denotes independently correct, W denotes a wrong publication, and A denotes abstention. All five conditions share each assignment’s edit scope, example labels and acceptance properties.

| Family | Language | Direct | Direct + blind retry | Direct + witness | Compiler only | Workflow |
|---|---|---:|---:|---:|---:|---:|
| feed_hopper | GPT++ | A/1 | A/2 | A/2 | A/0 | A/1 |
| feed_hopper | Typed Python | A/1 | A/2 | A/2 | A/0 | A/1 |
| feed_hopper | Rust | A/1 | A/2 | A/2 | A/0 | A/1 |
| mirror_carriage | GPT++ | A/1 | A/2 | A/2 | C/0 | C/0 |
| mirror_carriage | Typed Python | C/1 | C/1 | C/1 | C/0 | C/0 |
| mirror_carriage | Rust | C/1 | C/1 | C/1 | C/0 | C/0 |
| proof_sheet | GPT++ | A/1 | A/2 | A/2 | C/0 | C/0 |
| proof_sheet | Typed Python | A/1 | A/2 | A/2 | C/0 | C/0 |
| proof_sheet | Rust | A/1 | A/2 | A/2 | C/0 | C/0 |
| seal_press | GPT++ | A/1 | A/2 | A/2 | A/0 | A/1 |
| seal_press | Typed Python | A/1 | A/2 | A/2 | A/0 | A/1 |
| seal_press | Rust | A/1 | A/2 | A/2 | A/0 | A/1 |
| service_gap | GPT++ | A/1 | A/2 | A/2 | A/0 | A/1 |
| service_gap | Typed Python | A/1 | A/2 | C/2 | A/0 | C/1 |
| service_gap | Rust | A/1 | A/2 | A/2 | A/0 | C/1 |
| weighbridge | GPT++ | C/1 | C/1 | C/1 | C/0 | C/0 |
| weighbridge | Typed Python | C/1 | C/1 | C/1 | C/0 | C/0 |
| weighbridge | Rust | C/1 | C/1 | C/1 | C/0 | C/0 |
