# Frozen GPT++ expressions on the extended language

The compiler now accepts explicit Boolean-to-integer conversion and checked integer minimum, maximum and clamp operations. These features were chosen after inspecting the original model failures. This retrospective used the original site IDs, expressions and source programs and made zero new model calls. All original tokens remain charged.

| Task block | Model | Before | First answers now accepted | Final accepted | Charged input | Charged output | Tokens/accept |
|---|---|---:|---:|---:|---:|---:|---:|
| historical | qwen2.5-coder:7b | 0/3 | 0/3 | 0/3 | 4,123 | 158 | undefined |
| historical | starcoder2:3b | 0/3 | 0/3 | 0/3 | 4,510 | 127 | undefined |
| arithmetic | qwen2.5-coder:7b | 0/3 | 1/3 | 3/3 | 2,952 | 153 | 1,035.0 |
| arithmetic | starcoder2:3b | 0/3 | 0/3 | 0/3 | 3,226 | 120 | undefined |

| Model | Task | Selected attempt | Final outcome | Additional direct checks passed |
|---|---|---:|---|---:|
| qwen2.5-coder:7b | redis_lru_timestamp | — | wrong_answer | 0 |
| qwen2.5-coder:7b | go_footer_year_end | — | wrong_answer | 0 |
| qwen2.5-coder:7b | fastled_fixed_scale | — | wrong_answer | 0 |
| starcoder2:3b | redis_lru_timestamp | — | wrong_answer | 0 |
| starcoder2:3b | go_footer_year_end | — | wrong_answer | 0 |
| starcoder2:3b | fastled_fixed_scale | — | wrong_answer | 0 |
| qwen2.5-coder:7b | half_open_windows | 2 | accepted | 405 |
| qwen2.5-coder:7b | timeout_quantization | 2 | accepted | 305 |
| qwen2.5-coder:7b | bounded_accumulator | 1 | accepted | 169 |
| starcoder2:3b | half_open_windows | — | wrong_answer | 0 |
| starcoder2:3b | timeout_quantization | — | wrong_answer | 0 |
| starcoder2:3b | bounded_accumulator | — | wrong_answer | 0 |

The comparison uses familiar spellings present in the material that motivated the change. It measures compiler compatibility with those saved proposals. It leaves open whether fresh models choose effective repairs on independent tasks or use fewer tokens than Python or Rust.
