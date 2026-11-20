# Catalog-guided expression edits

18 fresh model calls on the three v9 development tasks. Every request includes the target, the public examples and the selectable expression list. Counts include every failed call.

## qwen2.5-coder:7b

| Language | Valid sites | Accepted | Input tokens | Output tokens | Tokens/accept | Decoder schema bytes |
|---|---|---|---|---|---|---|
| gpp | 3 | 0/3 | 1367 | 140 | undefined | 644 |
| python | 3 | 0/3 | 1361 | 72 | undefined | 663 |
| rust | 3 | 0/3 | 1545 | 91 | undefined | 693 |

| Comparator for GPT++ catalog | Acceptance difference, pp [95% interval] | Tokens/accept ratio [95% interval] | Gate |
|---|---|---|---|
| python_catalog | 0.0000 [0.0000, 0.0000] | undefined | unestimable |
| rust_catalog | 0.0000 [0.0000, 0.0000] | undefined | unestimable |
| gpp_locate | 0.0000 [0.0000, 0.0000] | undefined | unestimable |
| gpp_combined | 0.0000 [0.0000, 0.0000] | undefined | unestimable |
| python_full | 0.0000 [0.0000, 0.0000] | undefined | unestimable |
| rust_full | 0.0000 [0.0000, 0.0000] | undefined | unestimable |

## starcoder2:3b

| Language | Valid sites | Accepted | Input tokens | Output tokens | Tokens/accept | Decoder schema bytes |
|---|---|---|---|---|---|---|
| gpp | 3 | 0/3 | 1432 | 74 | undefined | 644 |
| python | 3 | 0/3 | 1403 | 81 | undefined | 663 |
| rust | 3 | 0/3 | 1641 | 75 | undefined | 693 |

| Comparator for GPT++ catalog | Acceptance difference, pp [95% interval] | Tokens/accept ratio [95% interval] | Gate |
|---|---|---|---|
| python_catalog | 0.0000 [0.0000, 0.0000] | undefined | unestimable |
| rust_catalog | 0.0000 [0.0000, 0.0000] | undefined | unestimable |
| gpp_locate | 0.0000 [0.0000, 0.0000] | undefined | unestimable |
| gpp_combined | 0.0000 [0.0000, 0.0000] | undefined | unestimable |
| python_full | 0.0000 [0.0000, 0.0000] | undefined | unestimable |
| rust_full | 0.0000 [0.0000, 0.0000] | undefined | unestimable |
