# Completion-boundary pilot

56/56 assigned trials completed for qwen2.5-coder:7b, seed 42, across eight tasks and seven conditions.

## Assigned trials and observed costs

| Condition | Completed | Calls | First accepted / assigned | Final accepted / assigned | Input tokens | Output tokens | All tokens | Tokens/accepted | Model s | Public tool s | Workflow s | Held-out s | Workflow s/accepted | Workflow + held-out s/accepted |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| gpp_open | 8/8 | 15 | 1/8 (12.5%) | 1/8 (12.5%) | 3838 | 1404 | 5242 | 5,242.00 | 65.33 | 0.31 | 65.65 | 0.33 | 65.65 | 65.98 |
| gpp_stop | 8/8 | 15 | 1/8 (12.5%) | 1/8 (12.5%) | 3624 | 857 | 4481 | 4,481.00 | 42.84 | 0.73 | 43.57 | 0.39 | 43.57 | 43.96 |
| rust_open | 8/8 | 15 | 0/8 (0.0%) | 1/8 (12.5%) | 3926 | 1981 | 5907 | 5,907.00 | 87.20 | 10.06 | 97.26 | 4.29 | 97.26 | 101.55 |
| rust_stop | 8/8 | 12 | 3/8 (37.5%) | 3/8 (37.5%) | 2396 | 612 | 3008 | 1,002.67 | 31.55 | 38.07 | 69.62 | 9.38 | 23.21 | 26.33 |
| python_open | 8/8 | 13 | 3/8 (37.5%) | 4/8 (50.0%) | 2498 | 612 | 3110 | 777.50 | 31.67 | 14.38 | 46.05 | 0.12 | 11.51 | 11.54 |
| python_stop | 8/8 | 13 | 3/8 (37.5%) | 4/8 (50.0%) | 2498 | 563 | 3061 | 765.25 | 28.37 | 14.95 | 43.33 | 0.12 | 10.83 | 10.86 |
| gpp_projected_stop | 8/8 | 15 | 1/8 (12.5%) | 1/8 (12.5%) | 3502 | 770 | 4272 | 4,272.00 | 40.69 | 0.43 | 41.12 | 0.40 | 41.12 | 41.52 |

All calls and repairs contribute to totals. Model time and public tool time are included in workflow time. The final column also includes held-out checking. Input and output tokens have equal weight here. Financial cost would require a pricing model.

## Paired comparisons

Ratios use the first condition as numerator. Acceptance differences are percentage points. Brackets are 95% percentile intervals using 10,000 task-cluster draws (seed 20261119). Each draw keeps all matched observations of a task together. Undefined draws may occupy either tail. The screen requires an acceptance lower bound of at least −2 pp and a tokens/accepted upper bound of at most 0.8000.

| Numerator | Comparator | Matched/assigned | Tasks | Final acceptance Δ (pp) | All-token ratio | Tokens/accepted ratio | Workflow s/accepted ratio | Pilot screen |
|---|---|---|---|---|---|---|---|---|
| gpp_stop | gpp_open | 8/8 | 8 | 0.0000 [0.0000, 0.0000] | 0.8548 [0.7401, 0.9663] | 0.8548 [0.0000, ∞] (3499 undefined draws) | 0.6637 [0.0000, ∞] (3499 undefined draws) | bounds not both met |
| rust_stop | rust_open | 8/8 | 8 | 25.0000 [0.0000, 62.5000] | 0.5092 [0.3970, 0.6606] | 0.1697 [0.0000, ∞] (3520 undefined draws) | 0.2386 [0.0000, ∞] (3520 undefined draws) | bounds not both met |
| python_stop | python_open | 8/8 | 8 | 0.0000 [0.0000, 0.0000] | 0.9842 [0.9603, 1.0000] | 0.9842 [0.9594, 1.0000] (30 undefined draws) | 0.9408 [0.8671, 1.0241] (30 undefined draws) | bounds not both met |
| gpp_stop | python_stop | 8/8 | 8 | -37.5000 [-87.5000, 12.5000] | 1.4639 [0.9783, 2.2595] | 5.8556 [0.0000, ∞] (3524 undefined draws) | 4.0221 [0.0000, ∞] (3524 undefined draws) | bounds not both met |
| gpp_stop | rust_stop | 8/8 | 8 | -25.0000 [-62.5000, 0.0000] | 1.4897 [1.1452, 2.1046] | 4.4691 [0.0000, ∞] (3499 undefined draws) | 1.8773 [0.0000, ∞] (3499 undefined draws) | bounds not both met |
| gpp_projected_stop | python_stop | 8/8 | 8 | -37.5000 [-75.0000, -12.5000] | 1.3956 [1.1292, 1.8817] | 5.5825 [0.0000, ∞] (3438 undefined draws) | 3.7964 [0.0000, ∞] (3438 undefined draws) | bounds not both met |

## Attempt and stop outcomes

| Condition | Attempt outcome | Calls | Terminal failures |
|---|---|---|---|
| gpp_open | accepted | 1 | 0 |
| gpp_open | check_error | 13 | 7 |
| gpp_open | wrong_answer | 1 | 0 |
| gpp_projected_stop | accepted | 1 | 0 |
| gpp_projected_stop | check_error | 10 | 5 |
| gpp_projected_stop | wrong_answer | 4 | 2 |
| gpp_stop | accepted | 1 | 0 |
| gpp_stop | check_error | 9 | 5 |
| gpp_stop | wrong_answer | 5 | 2 |
| python_open | accepted | 4 | 0 |
| python_open | check_error | 1 | 1 |
| python_open | runtime_error | 2 | 1 |
| python_open | wrong_answer | 6 | 2 |
| python_stop | accepted | 4 | 0 |
| python_stop | runtime_error | 2 | 1 |
| python_stop | wrong_answer | 7 | 3 |
| rust_open | accepted | 1 | 0 |
| rust_open | check_error | 12 | 5 |
| rust_open | heldout_wrong_answer | 1 | 1 |
| rust_open | wrong_answer | 1 | 1 |
| rust_stop | accepted | 3 | 0 |
| rust_stop | heldout_wrong_answer | 1 | 1 |
| rust_stop | wrong_answer | 8 | 4 |

| Condition | Generation stop reason | Calls |
|---|---|---|
| gpp_open | stop | 15 |
| gpp_projected_stop | stop | 15 |
| gpp_stop | stop | 15 |
| python_open | stop | 13 |
| python_stop | stop | 13 |
| rust_open | stop | 15 |
| rust_stop | stop | 12 |

## Cost of the public-feedback repair

The first-call columns count the observed initial calls and their acceptance. The repair columns count the additional calls, tokens and accepted trials.

| Condition | First-call tokens | First accepted | First-call tokens/accepted | Repair calls | Additional tokens | Additional accepted |
|---|---|---|---|---|---|---|
| gpp_open | 2307 | 1 | 2,307.00 | 7 | 2935 | 0 |
| gpp_stop | 2056 | 1 | 2,056.00 | 7 | 2425 | 0 |
| rust_open | 2463 | 0 | undefined | 7 | 3444 | 1 |
| rust_stop | 1829 | 3 | 609.67 | 4 | 1179 | 0 |
| python_open | 1650 | 3 | 550.00 | 5 | 1460 | 1 |
| python_stop | 1650 | 3 | 550.00 | 5 | 1411 | 1 |
| gpp_projected_stop | 1937 | 1 | 1,937.00 | 7 | 2335 | 0 |
