# Scalar program runtime and memory

Each correct reference runs two million calls in a checksum loop. Every implementation passed the original public and withheld cases, and all checksum results agree. Runtime is the median of three process executions including startup. Peak resident memory is measured by macOS time -l. Native builds use optimization level 2 and checked signed arithmetic.

| Task | Language | Build/check s | Runtime median s | Peak RSS median MiB |
|---|---|---:|---:|---:|
| redis_lru_timestamp | gpp | 0.258 | 0.0075 | 1.30 |
| redis_lru_timestamp | rust | 0.108 | 0.0080 | 1.47 |
| redis_lru_timestamp | python | 0.028 | 0.3187 | 11.59 |
| fastled_fixed_scale | gpp | 0.253 | 0.0071 | 1.31 |
| fastled_fixed_scale | rust | 0.114 | 0.0078 | 1.48 |
| fastled_fixed_scale | python | 0.029 | 0.3138 | 11.61 |
| go_footer_year_end | gpp | 0.245 | 0.0070 | 1.31 |
| go_footer_year_end | rust | 0.102 | 0.0083 | 1.48 |
| go_footer_year_end | python | 0.027 | 0.2812 | 11.61 |

The single build measurement is descriptive. Python's entry is bytecode compilation. GPT++ and Rust produce native executables. The loops cover these declared scalar inputs, and compiler optimization can simplify them. Tiny native execution times are sensitive to process startup and host scheduling. General application performance remains unmeasured.
