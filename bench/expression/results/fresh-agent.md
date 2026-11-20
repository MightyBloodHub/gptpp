# Native expression repairs on three new scalar contracts

Each contract has two callers, three visible tests and twelve withheld checks. Two models ran all three contracts in each language. All failed calls are included.

| Model | Language | First accepted | Final accepted | Retries | Input tokens | Output tokens | Tokens/accept | Workflow seconds | Model seconds |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| qwen2.5-coder:7b | gpp | 0/3 | 0/3 | 3 | 2,952 | 153 | undefined | 15.47 | 14.89 |
| qwen2.5-coder:7b | python | 1/3 | 2/3 | 2 | 2,357 | 107 | 1,232.0 | 14.41 | 10.39 |
| qwen2.5-coder:7b | rust | 0/3 | 1/3 | 3 | 3,320 | 156 | 3,476.0 | 47.52 | 16.27 |
| starcoder2:3b | gpp | 0/3 | 0/3 | 3 | 3,226 | 120 | undefined | 6.82 | 6.25 |
| starcoder2:3b | python | 0/3 | 0/3 | 3 | 2,938 | 116 | undefined | 8.74 | 4.97 |
| starcoder2:3b | rust | 0/3 | 0/3 | 3 | 3,566 | 118 | undefined | 32.68 | 6.17 |

| Model | Task | Language | First public check | Final result |
|---|---|---|---|---|
| qwen2.5-coder:7b | half_open_windows | gpp | check_error | check_error |
| qwen2.5-coder:7b | timeout_quantization | python | pass | accepted |
| qwen2.5-coder:7b | timeout_quantization | rust | check_error | check_error |
| qwen2.5-coder:7b | half_open_windows | python | runtime_error | runtime_error |
| qwen2.5-coder:7b | timeout_quantization | gpp | check_error | check_error |
| qwen2.5-coder:7b | bounded_accumulator | rust | wrong_answer | accepted |
| qwen2.5-coder:7b | half_open_windows | rust | check_error | check_error |
| qwen2.5-coder:7b | bounded_accumulator | gpp | check_error | check_error |
| qwen2.5-coder:7b | bounded_accumulator | python | check_error | accepted |
| starcoder2:3b | half_open_windows | gpp | wrong_answer | wrong_answer |
| starcoder2:3b | timeout_quantization | python | wrong_answer | wrong_answer |
| starcoder2:3b | timeout_quantization | rust | check_error | check_error |
| starcoder2:3b | half_open_windows | python | wrong_answer | wrong_answer |
| starcoder2:3b | timeout_quantization | gpp | wrong_answer | wrong_answer |
| starcoder2:3b | bounded_accumulator | rust | wrong_answer | wrong_answer |
| starcoder2:3b | half_open_windows | rust | check_error | check_error |
| starcoder2:3b | bounded_accumulator | gpp | wrong_answer | wrong_answer |
| starcoder2:3b | bounded_accumulator | python | check_error | check_error |

These three locally authored tasks cover scalar arithmetic and interval handling. The block was frozen before inference on these tasks. It does not measure general software development, and a cost per accepted edit is undefined for groups with no accepted change.
