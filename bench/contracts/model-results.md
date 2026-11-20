# Local models repairing finite contracts

Each model received the three original modules and their declared contracts. The compiler listed available edit sites, checked the generated replacement and allowed at most one diagnostic retry. Independent direct evaluation checked each selected expression over the complete declared domain.

| Model | First accepted | Final accepted | Calls | Input tokens | Output tokens | Tokens/accept | CLI seconds |
|---|---:|---:|---:|---:|---:|---:|---:|
| qwen2.5-coder:7b | 1/3 | 1/3 | 5 | 1,633 | 112 | 1,745.0 | 18.38 |
| starcoder2:3b | 0/3 | 0/3 | 6 | 2,231 | 183 | undefined | 8.01 |

| Model | Task | First validation | Final validation | Accepted edit | Extra inputs passing |
|---|---|---|---|---|---:|
| qwen2.5-coder:7b | offset_tick | counterexample | counterexample | — | — |
| qwen2.5-coder:7b | has_room | pass | pass | `limit - used > 0` | 5/5 |
| qwen2.5-coder:7b | block_index | counterexample | counterexample | — | — |
| starcoder2:3b | offset_tick | check_error | check_error | — | — |
| starcoder2:3b | has_room | counterexample | counterexample | — | — |
| starcoder2:3b | block_index | check_error | check_error | — | — |

A harness assertion interrupted the original Qwen/capacity collection before it archived that assignment. The completed Qwen/carry record was retained. The affected assignment was recollected under the same protocol. The table covers the six archived trials. Usage for the interrupted assignment is unavailable.

All failed calls in the six archived trials contribute to the token totals. The five extra inputs per task were scorer-only checks outside the contracts. A finite certificate covers the declared tuples. This small development run has no matched model comparison against Python, Rust or unassisted generation.
