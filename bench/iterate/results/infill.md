# Matched GPT++ authoring replication

40/40 assigned trials completed. The primary numerator is gpp_fim and the secondary numerator is gpp_projected. Both compare with python_fim, rust_fim and gpp_chat on the same task, model and seed. All attempts contribute usage.

Brackets are 95% percentile intervals from 10,000 deterministic task-cluster resamples (seed 20261119). Each task retains its model and seed runs. Draws with an undefined ratio may occupy either tail. The pilot screens for an acceptance lower bound of −2 pp or greater and a tokens/accepted upper ratio of 0.8000 or lower.

Tokens are Ollama's reported input and generated token counts, including rendered context and all retries. The total weights input and output equally. Wall time includes model calls and public tool checks. The log records held-out scoring time separately. Adapters differ in validation, compilation and process startup. Financial savings require a declared cost model and independent qualification.

## All models

| Condition | Calls | First accepted | Final accepted | Input tokens | Output tokens | All tokens | Tokens/accepted | Wall s/accepted | Model s | Tool s | Wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gpp_fim | 16 | 0/8 (0.0%) | 0/8 (0.0%) | 4584 | 2206 | 6790 | undefined | undefined | 98.58 | 0.46 | 99.05 |
| gpp_chat | 15 | 1/8 (12.5%) | 1/8 (12.5%) | 4031 | 786 | 4817 | 4,817.00 | 43.17 | 42.27 | 0.90 | 43.17 |
| gpp_projected | 16 | 0/8 (0.0%) | 0/8 (0.0%) | 3812 | 1048 | 4860 | undefined | undefined | 50.00 | 0.64 | 50.64 |
| python_fim | 11 | 4/8 (50.0%) | 4/8 (50.0%) | 2328 | 1154 | 3482 | 870.50 | 14.80 | 53.13 | 6.06 | 59.20 |
| rust_fim | 16 | 0/8 (0.0%) | 0/8 (0.0%) | 4160 | 2612 | 6772 | undefined | undefined | 112.42 | 0.01 | 112.43 |

| Numerator | Comparator | Matched/assigned | Tasks | Acceptance Δ (pp) | All-token ratio | Tokens/accepted ratio | Wall s/accepted ratio | Acceptance and token bounds |
|---|---|---|---|---|---|---|---|---|
| gpp_fim | python_fim | 8/8 | 8 | -50.0000 [-87.5000, -12.5000] | 1.9500 [1.1021, 4.0914] | undefined | undefined | unestimable |
| gpp_fim | rust_fim | 8/8 | 8 | 0.0000 [0.0000, 0.0000] | 1.0027 [0.8861, 1.1393] | undefined | undefined | unestimable |
| gpp_fim | gpp_chat | 8/8 | 8 | -12.5000 [-37.5000, 0.0000] | 1.4096 [1.0868, 1.8057] | undefined | undefined | unestimable |
| gpp_projected | python_fim | 8/8 | 8 | -50.0000 [-87.5000, -12.5000] | 1.3957 [1.0153, 2.3983] | undefined | undefined | unestimable |
| gpp_projected | rust_fim | 8/8 | 8 | 0.0000 [0.0000, 0.0000] | 0.7177 [0.5877, 0.8762] | undefined | undefined | unestimable |
| gpp_projected | gpp_chat | 8/8 | 8 | -12.5000 [-37.5000, 0.0000] | 1.0089 [0.8579, 1.2188] | undefined | undefined | unestimable |

## qwen2.5-coder:7b

| Condition | Calls | First accepted | Final accepted | Input tokens | Output tokens | All tokens | Tokens/accepted | Wall s/accepted | Model s | Tool s | Wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gpp_fim | 16 | 0/8 (0.0%) | 0/8 (0.0%) | 4584 | 2206 | 6790 | undefined | undefined | 98.58 | 0.46 | 99.05 |
| gpp_chat | 15 | 1/8 (12.5%) | 1/8 (12.5%) | 4031 | 786 | 4817 | 4,817.00 | 43.17 | 42.27 | 0.90 | 43.17 |
| gpp_projected | 16 | 0/8 (0.0%) | 0/8 (0.0%) | 3812 | 1048 | 4860 | undefined | undefined | 50.00 | 0.64 | 50.64 |
| python_fim | 11 | 4/8 (50.0%) | 4/8 (50.0%) | 2328 | 1154 | 3482 | 870.50 | 14.80 | 53.13 | 6.06 | 59.20 |
| rust_fim | 16 | 0/8 (0.0%) | 0/8 (0.0%) | 4160 | 2612 | 6772 | undefined | undefined | 112.42 | 0.01 | 112.43 |

| Numerator | Comparator | Matched/assigned | Tasks | Acceptance Δ (pp) | All-token ratio | Tokens/accepted ratio | Wall s/accepted ratio | Acceptance and token bounds |
|---|---|---|---|---|---|---|---|---|
| gpp_fim | python_fim | 8/8 | 8 | -50.0000 [-87.5000, -12.5000] | 1.9500 [1.1021, 4.0914] | undefined | undefined | unestimable |
| gpp_fim | rust_fim | 8/8 | 8 | 0.0000 [0.0000, 0.0000] | 1.0027 [0.8861, 1.1393] | undefined | undefined | unestimable |
| gpp_fim | gpp_chat | 8/8 | 8 | -12.5000 [-37.5000, 0.0000] | 1.4096 [1.0868, 1.8057] | undefined | undefined | unestimable |
| gpp_projected | python_fim | 8/8 | 8 | -50.0000 [-87.5000, -12.5000] | 1.3957 [1.0153, 2.3983] | undefined | undefined | unestimable |
| gpp_projected | rust_fim | 8/8 | 8 | 0.0000 [0.0000, 0.0000] | 0.7177 [0.5877, 0.8762] | undefined | undefined | unestimable |
| gpp_projected | gpp_chat | 8/8 | 8 | -12.5000 [-37.5000, 0.0000] | 1.0089 [0.8579, 1.2188] | undefined | undefined | unestimable |

## Synthesis

| Condition | Calls | First accepted | Final accepted | Input tokens | Output tokens | All tokens | Tokens/accepted | Wall s/accepted | Model s | Tool s | Wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gpp_fim | 8 | 0/4 (0.0%) | 0/4 (0.0%) | 1935 | 1088 | 3023 | undefined | undefined | 47.04 | 0.10 | 47.13 |
| gpp_chat | 8 | 0/4 (0.0%) | 0/4 (0.0%) | 1970 | 501 | 2471 | undefined | undefined | 25.11 | 0.23 | 25.34 |
| gpp_projected | 8 | 0/4 (0.0%) | 0/4 (0.0%) | 1690 | 712 | 2402 | undefined | undefined | 31.71 | 0.25 | 31.96 |
| python_fim | 6 | 2/4 (50.0%) | 2/4 (50.0%) | 1321 | 987 | 2308 | 1,154.00 | 22.35 | 42.92 | 1.77 | 44.69 |
| rust_fim | 8 | 0/4 (0.0%) | 0/4 (0.0%) | 1705 | 1329 | 3034 | undefined | undefined | 56.60 | 0.00 | 56.60 |

| Numerator | Comparator | Matched/assigned | Tasks | Acceptance Δ (pp) | All-token ratio | Tokens/accepted ratio | Wall s/accepted ratio | Acceptance and token bounds |
|---|---|---|---|---|---|---|---|---|
| gpp_fim | python_fim | 4/4 | 4 | -50.0000 [-100.0000, 0.0000] | 1.3098 [0.6614, 5.8041] | undefined | undefined | unestimable |
| gpp_fim | rust_fim | 4/4 | 4 | 0.0000 [0.0000, 0.0000] | 0.9964 [0.8409, 1.2816] | undefined | undefined | unestimable |
| gpp_fim | gpp_chat | 4/4 | 4 | 0.0000 [0.0000, 0.0000] | 1.2234 [0.9075, 1.7482] | undefined | undefined | unestimable |
| gpp_projected | python_fim | 4/4 | 4 | -50.0000 [-100.0000, 0.0000] | 1.0407 [0.8195, 2.5739] | undefined | undefined | unestimable |
| gpp_projected | rust_fim | 4/4 | 4 | 0.0000 [0.0000, 0.0000] | 0.7917 [0.5064, 1.0630] | undefined | undefined | unestimable |
| gpp_projected | gpp_chat | 4/4 | 4 | 0.0000 [0.0000, 0.0000] | 0.9721 [0.7483, 1.1245] | undefined | undefined | unestimable |

## Maintenance

| Condition | Calls | First accepted | Final accepted | Input tokens | Output tokens | All tokens | Tokens/accepted | Wall s/accepted | Model s | Tool s | Wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gpp_fim | 8 | 0/4 (0.0%) | 0/4 (0.0%) | 2649 | 1118 | 3767 | undefined | undefined | 51.55 | 0.37 | 51.92 |
| gpp_chat | 7 | 1/4 (25.0%) | 1/4 (25.0%) | 2061 | 285 | 2346 | 2,346.00 | 17.83 | 17.16 | 0.67 | 17.83 |
| gpp_projected | 8 | 0/4 (0.0%) | 0/4 (0.0%) | 2122 | 336 | 2458 | undefined | undefined | 18.29 | 0.39 | 18.68 |
| python_fim | 5 | 2/4 (50.0%) | 2/4 (50.0%) | 1007 | 167 | 1174 | 587.00 | 7.25 | 10.22 | 4.29 | 14.51 |
| rust_fim | 8 | 0/4 (0.0%) | 0/4 (0.0%) | 2455 | 1283 | 3738 | undefined | undefined | 55.83 | 0.00 | 55.83 |

| Numerator | Comparator | Matched/assigned | Tasks | Acceptance Δ (pp) | All-token ratio | Tokens/accepted ratio | Wall s/accepted ratio | Acceptance and token bounds |
|---|---|---|---|---|---|---|---|---|
| gpp_fim | python_fim | 4/4 | 4 | -50.0000 [-100.0000, 0.0000] | 3.2087 [2.6317, 4.3595] | undefined | undefined | unestimable |
| gpp_fim | rust_fim | 4/4 | 4 | 0.0000 [0.0000, 0.0000] | 1.0078 [0.8581, 1.1259] | undefined | undefined | unestimable |
| gpp_fim | gpp_chat | 4/4 | 4 | -25.0000 [-75.0000, 0.0000] | 1.6057 [1.1026, 2.0040] | undefined | undefined | unestimable |
| gpp_projected | python_fim | 4/4 | 4 | -50.0000 [-100.0000, 0.0000] | 2.0937 [1.4718, 2.6807] | undefined | undefined | unestimable |
| gpp_projected | rust_fim | 4/4 | 4 | 0.0000 [0.0000, 0.0000] | 0.6576 [0.5582, 0.7835] | undefined | undefined | unestimable |
| gpp_projected | gpp_chat | 4/4 | 4 | -25.0000 [-75.0000, 0.0000] | 1.0477 [0.8626, 1.5194] | undefined | undefined | unestimable |

## Attempt outcomes

| Condition | Outcome | All attempts | Terminal failures |
|---|---|---|---|
| gpp_chat | accepted | 1 | 0 |
| gpp_chat | check_error | 8 | 4 |
| gpp_chat | wrong_answer | 6 | 3 |
| gpp_fim | check_error | 12 | 6 |
| gpp_fim | wrong_answer | 4 | 2 |
| gpp_projected | check_error | 10 | 5 |
| gpp_projected | wrong_answer | 6 | 3 |
| python_fim | accepted | 4 | 0 |
| python_fim | check_error | 4 | 2 |
| python_fim | heldout_wrong_answer | 1 | 1 |
| python_fim | wrong_answer | 2 | 1 |
| rust_fim | check_error | 16 | 8 |

| Condition | Generation stop | Calls |
|---|---|---|
| gpp_chat | stop | 15 |
| gpp_fim | length | 4 |
| gpp_fim | stop | 12 |
| gpp_projected | stop | 16 |
| python_fim | length | 3 |
| python_fim | stop | 8 |
| rust_fim | length | 3 |
| rust_fim | stop | 13 |

## Cost of the public-feedback repair

The first-call columns count the observed initial calls and their acceptance. The repair columns count the additional calls, tokens and accepted trials.

| Condition | First-call tokens | First accepted | First-call tokens/accepted | Repair calls | Additional tokens | Additional accepted |
|---|---|---|---|---|---|---|
| gpp_fim | 2702 | 0 | undefined | 8 | 4088 | 0 |
| gpp_chat | 2244 | 1 | 2,244.00 | 7 | 2573 | 0 |
| gpp_projected | 2043 | 0 | undefined | 8 | 2817 | 0 |
| python_fim | 1947 | 4 | 486.75 | 3 | 1535 | 0 |
| rust_fim | 2518 | 0 | undefined | 8 | 4254 | 0 |
