# multi-caller-policy-v7

8 paired task families per model. 24 public and 104 withheld examples. 384 cross-language reference checks. 112 trials and 164 measured model calls.

## qwen2.5-coder:7b

| Condition | First accepts | First-call tokens/accept | Retries | Added accepts | Retry tokens | Final accepts | Input tokens | Output tokens | All tokens/accept | Wall s/accept |
|---|---|---|---|---|---|---|---|---|---|---|
| gpp_rules | 0 | undefined | 6 | 0 | 3432 | 0/8 | 5482 | 663 | undefined | undefined |
| gpp_guard | 2 | 1,276.00 | 3 | 0 | 1743 | 2/8 | 3655 | 640 | 2,147.50 | 21.96 |
| gpp_full | 5 | 500.20 | 0 | 0 | 0 | 5/8 | 2053 | 448 | 500.20 | 6.01 |
| python_guard | 2 | 1,193.50 | 2 | 0 | 999 | 2/8 | 2736 | 650 | 1,693.00 | 24.77 |
| python_full | 3 | 762.00 | 2 | 0 | 889 | 3/8 | 2647 | 528 | 1,058.33 | 14.34 |
| rust_guard | 2 | 1,186.00 | 4 | 0 | 2004 | 2/8 | 3753 | 623 | 2,188.00 | 36.94 |
| rust_full | 5 | 465.00 | 3 | 0 | 1592 | 5/8 | 3352 | 565 | 783.40 | 13.92 |

| Comparator | Matched | Families | Acceptance Δ (pp) | Total token ratio | Tokens/accepted ratio (95% interval) | Time/accepted ratio | Gate |
|---|---|---|---|---|---|---|---|
| gpp_guard | 8/8 | 8 | -25.0000 [-62.5000, 0.0000] | 1.4307 [0.8954, 2.2856] | undefined | undefined | unestimable |
| gpp_full | 8/8 | 8 | -62.5000 [-87.5000, -25.0000] | 2.4570 [1.8758, 2.9722] | undefined | undefined | unestimable |
| python_guard | 8/8 | 8 | -25.0000 [-62.5000, 0.0000] | 1.8148 [1.3390, 2.5485] | undefined | undefined | unestimable |
| python_full | 8/8 | 8 | -37.5000 [-75.0000, -12.5000] | 1.9354 [1.4594, 2.5905] | undefined | undefined | unestimable |
| rust_guard | 8/8 | 8 | -25.0000 [-62.5000, 0.0000] | 1.4043 [1.1175, 1.8776] | undefined | undefined | unestimable |
| rust_full | 8/8 | 8 | -62.5000 [-100.0000, -25.0000] | 1.5688 [1.2531, 2.1568] | undefined | undefined | unestimable |

A positive shortfall is the additional improvement required to reach 20% savings.

| Comparator | 20% target in tokens/accept | Observed saving (%) | Shortfall (pp) | Shortfall (tokens/accept) |
|---|---|---|---|---|
| gpp_guard | 1,718.00 | undefined | undefined | undefined |
| gpp_full | 400.16 | undefined | undefined | undefined |
| python_guard | 1,354.40 | undefined | undefined | undefined |
| python_full | 846.67 | undefined | undefined | undefined |
| rust_guard | 1,750.40 | undefined | undefined | undefined |
| rust_full | 626.72 | undefined | undefined | undefined |

| Terminal outcome | gpp_rules | gpp_guard | gpp_full | python_guard | python_full | rust_guard | rust_full |
|---|---|---|---|---|---|---|---|
| accepted | 0 | 2 | 5 | 2 | 3 | 2 | 5 |
| check_error | 2 | 1 | 2 | 2 | 2 | 1 | 0 |
| heldout_wrong_answer | 0 | 0 | 0 | 1 | 1 | 0 | 0 |
| wrong_answer | 6 | 5 | 1 | 3 | 2 | 5 | 3 |

## starcoder2:3b

| Condition | First accepts | First-call tokens/accept | Retries | Added accepts | Retry tokens | Final accepts | Input tokens | Output tokens | All tokens/accept | Wall s/accept |
|---|---|---|---|---|---|---|---|---|---|---|
| gpp_rules | 0 | undefined | 2 | 0 | 1118 | 0/8 | 3757 | 142 | undefined | undefined |
| gpp_guard | 1 | 2,648.00 | 5 | 0 | 3080 | 1/8 | 5338 | 390 | 5,728.00 | 16.53 |
| gpp_full | 0 | undefined | 1 | 0 | 607 | 0/8 | 2915 | 438 | undefined | undefined |
| python_guard | 0 | undefined | 8 | 0 | 4091 | 0/8 | 5905 | 479 | undefined | undefined |
| python_full | 1 | 2,375.00 | 4 | 0 | 2106 | 1/8 | 3958 | 523 | 4,481.00 | 26.37 |
| rust_guard | 0 | undefined | 8 | 0 | 4539 | 0/8 | 6509 | 475 | undefined | undefined |
| rust_full | 0 | undefined | 4 | 0 | 2398 | 0/8 | 4338 | 647 | undefined | undefined |

| Comparator | Matched | Families | Acceptance Δ (pp) | Total token ratio | Tokens/accepted ratio (95% interval) | Time/accepted ratio | Gate |
|---|---|---|---|---|---|---|---|
| gpp_guard | 8/8 | 8 | -12.5000 [-37.5000, 0.0000] | 0.6807 [0.4346, 1.1502] | undefined | undefined | unestimable |
| gpp_full | 8/8 | 8 | 0.0000 [0.0000, 0.0000] | 1.1628 [0.6940, 1.8657] | undefined | undefined | unestimable |
| python_guard | 8/8 | 8 | 0.0000 [0.0000, 0.0000] | 0.6107 [0.4359, 0.8521] | undefined | undefined | unestimable |
| python_full | 8/8 | 8 | -12.5000 [-37.5000, 0.0000] | 0.8701 [0.5553, 1.4310] | undefined | undefined | unestimable |
| rust_guard | 8/8 | 8 | 0.0000 [0.0000, 0.0000] | 0.5583 [0.4028, 0.7628] | undefined | undefined | unestimable |
| rust_full | 8/8 | 8 | 0.0000 [0.0000, 0.0000] | 0.7821 [0.5730, 1.0235] | undefined | undefined | unestimable |

A positive shortfall is the additional improvement required to reach 20% savings.

| Comparator | 20% target in tokens/accept | Observed saving (%) | Shortfall (pp) | Shortfall (tokens/accept) |
|---|---|---|---|---|
| gpp_guard | 4,582.40 | undefined | undefined | undefined |
| gpp_full | undefined | undefined | undefined | undefined |
| python_guard | undefined | undefined | undefined | undefined |
| python_full | 3,584.80 | undefined | undefined | undefined |
| rust_guard | undefined | undefined | undefined | undefined |
| rust_full | undefined | undefined | undefined | undefined |

| Terminal outcome | gpp_rules | gpp_guard | gpp_full | python_guard | python_full | rust_guard | rust_full |
|---|---|---|---|---|---|---|---|
| accepted | 0 | 1 | 0 | 0 | 1 | 0 | 0 |
| check_error | 8 | 1 | 7 | 0 | 2 | 0 | 5 |
| heldout_wrong_answer | 0 | 1 | 0 | 0 | 0 | 0 | 0 |
| runtime_error | 0 | 0 | 0 | 0 | 1 | 0 | 0 |
| wrong_answer | 0 | 5 | 1 | 8 | 4 | 8 | 3 |

Wall time covers inference and public validation. Withheld evaluation is recorded separately. The intervals resample whole tasks. An undefined estimate means the run produced too few accepted edits to price a success. Costs use each model's own tokenizer.
