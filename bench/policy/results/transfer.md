# historical-upstream-transfer-v8

3 paired task families per model. 9 public and 52 withheld examples. 183 cross-language reference checks. 42 trials and 66 measured model calls.

## qwen2.5-coder:7b

Workflows selected on development data were gpp_full, python_full and rust_full.

| Condition | First accepts | First-call tokens/accept | Retries | Added accepts | Retry tokens | Final accepts | Input tokens | Output tokens | All tokens/accept | Wall s/accept |
|---|---|---|---|---|---|---|---|---|---|---|
| gpp_rules | 1 | 1,120.00 | 0 | 0 | 0 | 1/3 | 897 | 223 | 1,120.00 | 14.80 |
| gpp_guard | 1 | 991.00 | 1 | 0 | 601 | 1/3 | 1377 | 215 | 1,592.00 | 19.13 |
| gpp_full | 1 | 1,032.00 | 2 | 0 | 1409 | 1/3 | 2020 | 421 | 2,441.00 | 27.82 |
| python_guard | 1 | 1,121.00 | 0 | 0 | 0 | 1/3 | 733 | 388 | 1,121.00 | 23.12 |
| python_full | 0 | undefined | 2 | 0 | 1224 | 0/3 | 1737 | 377 | undefined | undefined |
| rust_guard | 0 | undefined | 2 | 0 | 1028 | 0/3 | 1681 | 349 | undefined | undefined |
| rust_full | 0 | undefined | 3 | 0 | 1764 | 0/3 | 2264 | 440 | undefined | undefined |

| Comparator | Matched | Families | Acceptance Δ (pp) | Total token ratio | Tokens/accepted ratio (95% interval) | Time/accepted ratio | Gate |
|---|---|---|---|---|---|---|---|
| gpp_rules | 3/3 | 3 | 0.0000 [-100.0000, 100.0000] | 2.1795 [0.7744, 2.7781] | 2.1795 [0.0000, ∞] (5572 undefined draws) | 1.8790 [0.0000, ∞] (5572 undefined draws) | bounds not both met |
| gpp_guard | 3/3 | 3 | 0.0000 [0.0000, 0.0000] | 1.5333 [0.9237, 2.5531] | 1.5333 [0.0000, ∞] (2983 undefined draws) | 1.4541 [0.0000, ∞] (2983 undefined draws) | bounds not both met |
| python_guard | 3/3 | 3 | 0.0000 [-100.0000, 100.0000] | 2.1775 [0.7443, 2.9016] | 2.1775 [0.0000, ∞] (5561 undefined draws) | 1.2030 [0.0000, ∞] (5561 undefined draws) | bounds not both met |
| python_full | 3/3 | 3 | 33.3333 [0.0000, 100.0000] | 1.1547 [1.0790, 1.2642] | undefined | undefined | unestimable |
| rust_guard | 3/3 | 3 | 33.3333 [0.0000, 100.0000] | 1.2025 [0.3789, 2.7021] | undefined | undefined | unestimable |
| rust_full | 3/3 | 3 | 33.3333 [0.0000, 100.0000] | 0.9027 [0.3986, 1.0653] | undefined | undefined | unestimable |

A positive shortfall is the additional improvement required to reach 20% savings.

| Comparator | 20% target in tokens/accept | Observed saving (%) | Shortfall (pp) | Shortfall (tokens/accept) |
|---|---|---|---|---|
| gpp_rules | 896.00 | -117.95 | 137.95 | 1,545.00 |
| gpp_guard | 1,273.60 | -53.33 | 73.33 | 1,167.40 |
| python_guard | 896.80 | -117.75 | 137.75 | 1,544.20 |
| python_full | undefined | undefined | undefined | undefined |
| rust_guard | undefined | undefined | undefined | undefined |
| rust_full | undefined | undefined | undefined | undefined |

0 of 10 caller retries received an exact derived target result. Other retries received the original excerpts.

| Terminal outcome | gpp_rules | gpp_guard | gpp_full | python_guard | python_full | rust_guard | rust_full |
|---|---|---|---|---|---|---|---|
| accepted | 1 | 1 | 1 | 1 | 0 | 0 | 0 |
| check_error | 2 | 1 | 0 | 1 | 0 | 1 | 0 |
| heldout_wrong_answer | 0 | 0 | 0 | 1 | 0 | 0 | 0 |
| wrong_answer | 0 | 1 | 2 | 0 | 3 | 2 | 3 |

## starcoder2:3b

Workflows selected on development data were gpp_guard, python_full and rust_full.

| Condition | First accepts | First-call tokens/accept | Retries | Added accepts | Retry tokens | Final accepts | Input tokens | Output tokens | All tokens/accept | Wall s/accept |
|---|---|---|---|---|---|---|---|---|---|---|
| gpp_rules | 0 | undefined | 1 | 0 | 697 | 0/3 | 1748 | 49 | undefined | undefined |
| gpp_guard | 0 | undefined | 2 | 0 | 1223 | 0/3 | 2129 | 151 | undefined | undefined |
| gpp_full | 0 | undefined | 1 | 0 | 497 | 0/3 | 1408 | 238 | undefined | undefined |
| python_guard | 0 | undefined | 2 | 0 | 1018 | 0/3 | 1784 | 158 | undefined | undefined |
| python_full | 0 | undefined | 2 | 0 | 1017 | 0/3 | 1811 | 121 | undefined | undefined |
| rust_guard | 0 | undefined | 3 | 0 | 1860 | 0/3 | 2644 | 218 | undefined | undefined |
| rust_full | 0 | undefined | 3 | 0 | 2195 | 0/3 | 2822 | 484 | undefined | undefined |

| Comparator | Matched | Families | Acceptance Δ (pp) | Total token ratio | Tokens/accepted ratio (95% interval) | Time/accepted ratio | Gate |
|---|---|---|---|---|---|---|---|
| gpp_rules | 3/3 | 3 | 0.0000 [0.0000, 0.0000] | 1.2688 [0.9896, 2.7430] | undefined | undefined | unestimable |
| gpp_full | 3/3 | 3 | 0.0000 [0.0000, 0.0000] | 1.3852 [1.0170, 2.0374] | undefined | undefined | unestimable |
| python_guard | 3/3 | 3 | 0.0000 [0.0000, 0.0000] | 1.1740 [1.0972, 1.2560] | undefined | undefined | unestimable |
| python_full | 3/3 | 3 | 0.0000 [0.0000, 0.0000] | 1.1801 [1.1193, 1.2302] | undefined | undefined | unestimable |
| rust_guard | 3/3 | 3 | 0.0000 [0.0000, 0.0000] | 0.7966 [0.3397, 1.0834] | undefined | undefined | unestimable |
| rust_full | 3/3 | 3 | 0.0000 [0.0000, 0.0000] | 0.6897 [0.3594, 1.0156] | undefined | undefined | unestimable |

A positive shortfall is the additional improvement required to reach 20% savings.

| Comparator | 20% target in tokens/accept | Observed saving (%) | Shortfall (pp) | Shortfall (tokens/accept) |
|---|---|---|---|---|
| gpp_rules | undefined | undefined | undefined | undefined |
| gpp_full | undefined | undefined | undefined | undefined |
| python_guard | undefined | undefined | undefined | undefined |
| python_full | undefined | undefined | undefined | undefined |
| rust_guard | undefined | undefined | undefined | undefined |
| rust_full | undefined | undefined | undefined | undefined |

0 of 14 caller retries received an exact derived target result. Other retries received the original excerpts.

| Terminal outcome | gpp_rules | gpp_guard | gpp_full | python_guard | python_full | rust_guard | rust_full |
|---|---|---|---|---|---|---|---|
| check_error | 3 | 1 | 2 | 2 | 0 | 0 | 0 |
| runtime_error | 0 | 0 | 0 | 0 | 1 | 0 | 0 |
| wrong_answer | 0 | 2 | 1 | 1 | 2 | 3 | 3 |

Wall time covers inference and public validation. Withheld evaluation is recorded separately. The intervals resample whole tasks. An undefined estimate means the run produced too few accepted edits to price a success. Costs use each model's own tokenizer.
