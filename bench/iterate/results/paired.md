# Fragment authoring pilot

64/64 assigned trials completed. Each comparison uses GPT++ fragment as its numerator and matches task, model and seed. All attempts contribute usage.

Brackets are 95% percentile intervals from 10,000 deterministic task-cluster resamples (seed 20261119). Each task retains its model and seed runs. Draws with an undefined ratio may occupy either tail. The pilot screens for an acceptance lower bound of −2 pp or greater and a tokens/accepted upper ratio of 0.8000 or lower.

Tokens are Ollama's reported input and generated token counts, including rendered context and all retries. The total weights input and output equally. Wall time includes model calls and public tool checks. The log records held-out scoring time separately. Adapters differ in validation, compilation and process startup. Financial savings require a declared cost model and independent qualification.

## All models

| Condition | Calls | First accepted | Final accepted | Input tokens | Output tokens | All tokens | Tokens/accepted | Wall s/accepted | Model s | Tool s | Wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gpp_fragment | 29 | 3/16 (18.8%) | 4/16 (25.0%) | 7898 | 1545 | 9443 | 2,360.75 | 16.75 | 64.90 | 2.10 | 67.00 |
| gpp_full | 32 | 0/16 (0.0%) | 1/16 (6.2%) | 15283 | 4461 | 19744 | 19,744.00 | 179.14 | 177.82 | 1.32 | 179.14 |
| python_fragment | 24 | 8/16 (50.0%) | 8/16 (50.0%) | 4888 | 800 | 5688 | 711.00 | 6.87 | 36.34 | 18.64 | 54.99 |
| rust_fragment | 28 | 4/16 (25.0%) | 4/16 (25.0%) | 6899 | 1262 | 8161 | 2,040.25 | 33.13 | 62.13 | 70.40 | 132.54 |

| Comparator | Matched/assigned | Tasks | Acceptance Δ (pp) | Tokens/accepted ratio | Wall s/accepted ratio | Acceptance and token bounds |
|---|---|---|---|---|---|---|
| gpp_full | 16/16 | 8 | 18.7500 [6.2500, 37.5000] | 0.1196 [0.0000, ∞] (3478 undefined draws) | 0.0935 [0.0000, ∞] (3478 undefined draws) | bounds not both met |
| python_fragment | 16/16 | 8 | -25.0000 [-62.5000, 0.0000] | 3.3203 [1.2035, 13.3538] (31 undefined draws) | 2.4371 [0.7991, 8.6868] (31 undefined draws) | bounds not both met |
| rust_fragment | 16/16 | 8 | 0.0000 [-18.7500, 18.7500] | 1.1571 [0.3812, 3.4486] (78 undefined draws) | 0.5055 [0.2039, 1.3755] (78 undefined draws) | bounds not both met |

## deepseek-coder:6.7b

| Condition | Calls | First accepted | Final accepted | Input tokens | Output tokens | All tokens | Tokens/accepted | Wall s/accepted | Model s | Tool s | Wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gpp_fragment | 15 | 1/8 (12.5%) | 1/8 (12.5%) | 4317 | 905 | 5222 | 5,222.00 | 36.23 | 35.16 | 1.06 | 36.23 |
| gpp_full | 16 | 0/8 (0.0%) | 0/8 (0.0%) | 8454 | 3460 | 11914 | undefined | undefined | 127.82 | 0.54 | 128.36 |
| python_fragment | 12 | 4/8 (50.0%) | 4/8 (50.0%) | 2502 | 400 | 2902 | 725.50 | 6.80 | 17.41 | 9.80 | 27.20 |
| rust_fragment | 14 | 2/8 (25.0%) | 2/8 (25.0%) | 3471 | 630 | 4101 | 2,050.50 | 29.74 | 26.62 | 32.85 | 59.47 |

| Comparator | Matched/assigned | Tasks | Acceptance Δ (pp) | Tokens/accepted ratio | Wall s/accepted ratio | Acceptance and token bounds |
|---|---|---|---|---|---|---|
| gpp_full | 8/8 | 8 | 12.5000 [0.0000, 37.5000] | undefined | undefined | unestimable |
| python_fragment | 8/8 | 8 | -37.5000 [-75.0000, -12.5000] | 7.1978 [0.0000, ∞] (3520 undefined draws) | 5.3266 [0.0000, ∞] (3520 undefined draws) | bounds not both met |
| rust_fragment | 8/8 | 8 | -12.5000 [-37.5000, 0.0000] | 2.5467 [0.0000, ∞] (3520 undefined draws) | 1.2182 [0.0000, ∞] (3520 undefined draws) | bounds not both met |

## llama3:latest

| Condition | Calls | First accepted | Final accepted | Input tokens | Output tokens | All tokens | Tokens/accepted | Wall s/accepted | Model s | Tool s | Wall s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gpp_fragment | 14 | 2/8 (25.0%) | 3/8 (37.5%) | 3581 | 640 | 4221 | 1,407.00 | 10.26 | 29.74 | 1.04 | 30.78 |
| gpp_full | 16 | 0/8 (0.0%) | 1/8 (12.5%) | 6829 | 1001 | 7830 | 7,830.00 | 50.78 | 50.00 | 0.78 | 50.78 |
| python_fragment | 12 | 4/8 (50.0%) | 4/8 (50.0%) | 2386 | 400 | 2786 | 696.50 | 6.95 | 18.93 | 8.85 | 27.78 |
| rust_fragment | 14 | 2/8 (25.0%) | 2/8 (25.0%) | 3428 | 632 | 4060 | 2,030.00 | 36.53 | 35.52 | 37.55 | 73.07 |

| Comparator | Matched/assigned | Tasks | Acceptance Δ (pp) | Tokens/accepted ratio | Wall s/accepted ratio | Acceptance and token bounds |
|---|---|---|---|---|---|---|
| gpp_full | 8/8 | 8 | 25.0000 [0.0000, 62.5000] | 0.1797 [0.0000, ∞] (3478 undefined draws) | 0.2020 [0.0000, ∞] (3478 undefined draws) | bounds not both met |
| python_fragment | 8/8 | 8 | -12.5000 [-50.0000, 25.0000] | 2.0201 [0.0000, ∞] (274 undefined draws) | 1.4771 [0.0000, ∞] (274 undefined draws) | bounds not both met |
| rust_fragment | 8/8 | 8 | 12.5000 [0.0000, 37.5000] | 0.6931 [0.0000, ∞] (991 undefined draws) | 0.2808 [0.0000, ∞] (991 undefined draws) | bounds not both met |

## Attempt outcomes

| Condition | Outcome | All attempts | Terminal failures |
|---|---|---|---|
| gpp_fragment | accepted | 4 | 0 |
| gpp_fragment | check_error | 7 | 3 |
| gpp_fragment | wrong_answer | 18 | 9 |
| gpp_full | accepted | 1 | 0 |
| gpp_full | check_error | 21 | 11 |
| gpp_full | wrong_answer | 10 | 4 |
| python_fragment | accepted | 8 | 0 |
| python_fragment | check_error | 2 | 1 |
| python_fragment | wrong_answer | 14 | 7 |
| rust_fragment | accepted | 4 | 0 |
| rust_fragment | check_error | 5 | 2 |
| rust_fragment | wrong_answer | 19 | 10 |

| Condition | Generation stop | Calls |
|---|---|---|
| gpp_fragment | stop | 29 |
| gpp_full | length | 8 |
| gpp_full | stop | 24 |
| python_fragment | stop | 24 |
| rust_fragment | stop | 28 |

## Cost of the public-feedback repair

The first-call columns count the observed initial calls and their acceptance. The repair columns count the additional calls, tokens and accepted trials.

| Condition | First-call tokens | First accepted | First-call tokens/accepted | Repair calls | Additional tokens | Additional accepted |
|---|---|---|---|---|---|---|
| gpp_full | 8799 | 0 | undefined | 16 | 10945 | 1 |
| gpp_fragment | 4376 | 3 | 1,458.67 | 13 | 5067 | 1 |
| python_fragment | 3531 | 8 | 441.38 | 8 | 2157 | 0 |
| rust_fragment | 3816 | 4 | 954.00 | 12 | 4345 | 0 |
