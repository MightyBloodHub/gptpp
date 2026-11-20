# Generating checked expressions with public feedback

Three development tasks for each model and language. Accepted changes passed public and withheld checks. Every model call counts toward usage.

| Model | Language | First accepted | Final accepted | Retries | Input tokens | Output tokens | Tokens/accept | Workflow seconds | Model seconds |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| qwen2.5-coder:7b | python | 0/3 | 0/3 | 3 | 3,990 | 171 | undefined | 27.79 | 22.29 |
| qwen2.5-coder:7b | rust | 0/3 | 0/3 | 3 | 4,698 | 249 | undefined | 56.16 | 22.55 |
| qwen2.5-coder:7b | gpp | 0/3 | 0/3 | 3 | 4,123 | 158 | undefined | 16.60 | 15.55 |
| starcoder2:3b | python | 0/3 | 0/3 | 3 | 4,297 | 107 | undefined | 11.58 | 8.10 |
| starcoder2:3b | rust | 0/3 | 0/3 | 3 | 4,902 | 126 | undefined | 36.56 | 7.45 |
| starcoder2:3b | gpp | 0/3 | 0/3 | 3 | 4,510 | 127 | undefined | 7.03 | 6.52 |

| Task | Model | Language | First public check | Final result |
|---|---|---|---|---|
| redis_lru_timestamp | qwen2.5-coder:7b | python | wrong_answer | wrong_answer |
| go_footer_year_end | qwen2.5-coder:7b | rust | check_error | wrong_answer |
| go_footer_year_end | qwen2.5-coder:7b | python | wrong_answer | wrong_answer |
| redis_lru_timestamp | qwen2.5-coder:7b | rust | wrong_answer | wrong_answer |
| redis_lru_timestamp | qwen2.5-coder:7b | gpp | wrong_answer | wrong_answer |
| go_footer_year_end | qwen2.5-coder:7b | gpp | wrong_answer | wrong_answer |
| fastled_fixed_scale | qwen2.5-coder:7b | rust | check_error | check_error |
| fastled_fixed_scale | qwen2.5-coder:7b | python | wrong_answer | wrong_answer |
| fastled_fixed_scale | qwen2.5-coder:7b | gpp | wrong_answer | wrong_answer |
| redis_lru_timestamp | starcoder2:3b | python | check_error | check_error |
| go_footer_year_end | starcoder2:3b | rust | check_error | check_error |
| go_footer_year_end | starcoder2:3b | python | wrong_answer | wrong_answer |
| redis_lru_timestamp | starcoder2:3b | rust | wrong_answer | wrong_answer |
| redis_lru_timestamp | starcoder2:3b | gpp | wrong_answer | wrong_answer |
| go_footer_year_end | starcoder2:3b | gpp | wrong_answer | wrong_answer |
| fastled_fixed_scale | starcoder2:3b | rust | wrong_answer | wrong_answer |
| fastled_fixed_scale | starcoder2:3b | python | check_error | check_error |
| fastled_fixed_scale | starcoder2:3b | gpp | wrong_answer | wrong_answer |

The earlier one-shot catalog accepted zero changes in all six model/language groups. This follow-up changes caller context, public observations, syntax guidance and retry policy together. The same three previously inspected extracts appear in both studies. Timing includes model loading and local validation and depends on toolchain, cache and host. These observations do not establish a general advantage for any language.
