# Same-failure caller retry comparison

The alternate retry replaces the original caller source excerpt with an exact necessary leaf result. All 112 v7 first calls were screened using their public failures.

| Model | Trials | First public caller failures | Exact retries | Unsupported |
|---|---:|---:|---:|---:|
| qwen2.5-coder:7b | 56 | 20 | 8 | 12 |
| starcoder2:3b | 56 | 32 | 7 | 25 |

| Exact-retry cohort | Excerpt input / output tokens | Fact input / output tokens | Accepted before / after | Gains / losses |
|---|---:|---:|---:|---:|
| qwen2.5-coder:7b | 4,065 / 426 | 2,967 / 435 | 0 / 0 | 0 / 0 |
| starcoder2:3b | 3,761 / 245 | 2,710 / 247 | 0 / 0 | 0 / 0 |

| Model, full workflow | Accepted before / after | Total tokens before / after | Tokens per accepted edit before / after |
|---|---:|---:|---:|
| qwen2.5-coder:7b | 19 / 19 | 27,795 / 26,706 | 1,462.9 / 1,405.6 |
| starcoder2:3b | 2 / 2 | 35,814 / 34,765 | 17,907.0 / 17,382.5 |

The full-workflow calculation substitutes only the measured exact retries. It retains the archived initial calls and every unsupported retry. Per-model totals combine all seven arms; the same task appears in several arms. Each model has one sample per eligible cell. These token and acceptance differences describe the recorded failures on this corpus. [Protocol](../retry-obligations-protocol.md) · [Paired retry archive](retry-obligations.jsonl) · [Original attempts](policy.jsonl)
