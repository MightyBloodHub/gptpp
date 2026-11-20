# Expression-edit benchmark results

3 tasks, 72 assigned trials and 92 local model calls. 9 public and 43 withheld examples. 156 cross-language reference observations. Given-site trials receive the expression location. Separate and combined selection pay for the model to find it.

## qwen2.5-coder:7b

| Arm | Valid locations | Separate location tokens | First accepts | First total tokens | First tokens/accept | Retries | Final accepts | Final total tokens | Final tokens/accept | Model s | Local checks and overhead s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gpp_full | — | 0 | 0/3 | 1002 | undefined | 3 | 0/3 | 2684 | undefined | 21.10 | 0.48 |
| gpp_given | — | 0 | 0/3 | 821 | undefined | 0 | 0/3 | 821 | undefined | 4.48 | 0.11 |
| gpp_locate | 0/3 | 884 | 0/3 | 884 | undefined | 0 | 0/3 | 884 | undefined | 6.09 | 0.05 |
| gpp_combined | 0/3 | 0 | 0/3 | 1116 | undefined | 0 | 0/3 | 1116 | undefined | 14.31 | 0.03 |
| python_full | — | 0 | 0/3 | 985 | undefined | 1 | 0/3 | 1502 | undefined | 15.73 | 2.82 |
| python_given | — | 0 | 0/3 | 859 | undefined | 1 | 0/3 | 1341 | undefined | 10.47 | 1.71 |
| python_locate | 1/3 | 803 | 0/3 | 1047 | undefined | 1 | 0/3 | 1483 | undefined | 9.30 | 1.79 |
| python_combined | 0/3 | 0 | 0/3 | 876 | undefined | 0 | 0/3 | 876 | undefined | 12.81 | 0.00 |
| rust_full | — | 0 | 0/3 | 993 | undefined | 3 | 1/3 | 2795 | 2,795.00 | 28.05 | 24.24 |
| rust_given | — | 0 | 0/3 | 823 | undefined | 0 | 0/3 | 823 | undefined | 4.41 | 0.05 |
| rust_locate | 0/3 | 848 | 0/3 | 848 | undefined | 0 | 0/3 | 848 | undefined | 4.55 | 0.02 |
| rust_combined | 0/3 | 0 | 0/3 | 1146 | undefined | 0 | 0/3 | 1146 | undefined | 15.41 | 0.02 |

One-edit-attempt comparisons count location calls. A ratio of 0.80 represents 20% fewer tokens per accepted change. The gate also requires the paired 95% upper ratio bound to reach 0.80 and the lower acceptance difference to reach −2 percentage points.

| GPT++ arm | Comparator | Acceptance difference, pp [95% interval] | Tokens/accept ratio [95% interval] | Gate |
|---|---|---|---|---|
| gpp_locate | python_locate | 0.0000 [0.0000, 0.0000] | undefined | unestimable |
| gpp_locate | rust_locate | 0.0000 [0.0000, 0.0000] | undefined | unestimable |
| gpp_locate | python_full | 0.0000 [0.0000, 0.0000] | undefined | unestimable |
| gpp_locate | rust_full | 0.0000 [0.0000, 0.0000] | undefined | unestimable |
| gpp_locate | gpp_full | 0.0000 [0.0000, 0.0000] | undefined | unestimable |
| gpp_given | python_given | 0.0000 [0.0000, 0.0000] | undefined | unestimable |
| gpp_given | rust_given | 0.0000 [0.0000, 0.0000] | undefined | unestimable |
| gpp_given | gpp_full | 0.0000 [0.0000, 0.0000] | undefined | unestimable |
| gpp_combined | python_combined | 0.0000 [0.0000, 0.0000] | undefined | unestimable |
| gpp_combined | rust_combined | 0.0000 [0.0000, 0.0000] | undefined | unestimable |
| gpp_combined | gpp_locate | 0.0000 [0.0000, 0.0000] | undefined | unestimable |
| gpp_combined | gpp_full | 0.0000 [0.0000, 0.0000] | undefined | unestimable |

## starcoder2:3b

| Arm | Valid locations | Separate location tokens | First accepts | First total tokens | First tokens/accept | Retries | Final accepts | Final total tokens | Final tokens/accept | Model s | Local checks and overhead s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| gpp_full | — | 0 | 0/3 | 1072 | undefined | 3 | 0/3 | 2950 | undefined | 8.79 | 0.35 |
| gpp_given | — | 0 | 1/3 | 908 | 908.00 | 1 | 1/3 | 1484 | 1,484.00 | 2.81 | 0.22 |
| gpp_locate | 0/3 | 926 | 0/3 | 926 | undefined | 0 | 0/3 | 926 | undefined | 1.76 | 0.03 |
| gpp_combined | 0/3 | 0 | 0/3 | 943 | undefined | 0 | 0/3 | 943 | undefined | 1.57 | 0.03 |
| python_full | — | 0 | 0/3 | 1141 | undefined | 1 | 0/3 | 1990 | undefined | 9.18 | 3.43 |
| python_given | — | 0 | 0/3 | 930 | undefined | 3 | 0/3 | 2499 | undefined | 7.08 | 4.97 |
| python_locate | 0/3 | 873 | 0/3 | 873 | undefined | 0 | 0/3 | 873 | undefined | 2.03 | 0.00 |
| python_combined | 0/3 | 0 | 0/3 | 1112 | undefined | 0 | 0/3 | 1112 | undefined | 7.31 | 0.00 |
| rust_full | — | 0 | 0/3 | 1041 | undefined | 2 | 0/3 | 2377 | undefined | 7.82 | 16.86 |
| rust_given | — | 0 | 1/3 | 897 | 897.00 | 0 | 1/3 | 897 | 897.00 | 1.79 | 6.01 |
| rust_locate | 0/3 | 931 | 0/3 | 931 | undefined | 0 | 0/3 | 931 | undefined | 1.96 | 0.02 |
| rust_combined | 0/3 | 0 | 0/3 | 935 | undefined | 0 | 0/3 | 935 | undefined | 1.44 | 0.02 |

One-edit-attempt comparisons count location calls. A ratio of 0.80 represents 20% fewer tokens per accepted change. The gate also requires the paired 95% upper ratio bound to reach 0.80 and the lower acceptance difference to reach −2 percentage points.

| GPT++ arm | Comparator | Acceptance difference, pp [95% interval] | Tokens/accept ratio [95% interval] | Gate |
|---|---|---|---|---|
| gpp_locate | python_locate | 0.0000 [0.0000, 0.0000] | undefined | unestimable |
| gpp_locate | rust_locate | 0.0000 [0.0000, 0.0000] | undefined | unestimable |
| gpp_locate | python_full | 0.0000 [0.0000, 0.0000] | undefined | unestimable |
| gpp_locate | rust_full | 0.0000 [0.0000, 0.0000] | undefined | unestimable |
| gpp_locate | gpp_full | 0.0000 [0.0000, 0.0000] | undefined | unestimable |
| gpp_given | python_given | 33.3333 [0.0000, 100.0000] | undefined | unestimable |
| gpp_given | rust_given | 0.0000 [0.0000, 0.0000] | 1.0123 [0.0000, ∞] (2968 undefined draws) | bounds not both met |
| gpp_given | gpp_full | 33.3333 [0.0000, 100.0000] | undefined | unestimable |
| gpp_combined | python_combined | 0.0000 [0.0000, 0.0000] | undefined | unestimable |
| gpp_combined | rust_combined | 0.0000 [0.0000, 0.0000] | undefined | unestimable |
| gpp_combined | gpp_locate | 0.0000 [0.0000, 0.0000] | undefined | unestimable |
| gpp_combined | gpp_full | 0.0000 [0.0000, 0.0000] | undefined | unestimable |
