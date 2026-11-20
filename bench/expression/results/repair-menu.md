# Withheld audit of the frozen repair menus

After all six trials finished, the scorer tested every candidate in the archived menus. The two models received identical choices for each task. IDs refer to the original menu order. This retrospective audit did not affect the selections.

| Task | ID | Replaced expression | Candidate | Withheld result |
|---|---:|---|---|---|
| redis_lru_timestamp | 1 | `(clock + limit / 2) % limit` | `absolute + limit` | Passed every withheld case |
| redis_lru_timestamp | 2 | `(clock + limit / 2)` | `absolute + limit` | Passed every withheld case |
| fastled_fixed_scale | 1 | `level` | `level + 1` | scale_channel(128, 1, true) returned 0. Expected 1. |
| fastled_fixed_scale | 2 | `256` | `256 - 1` | scale_channel(128, 1, true) returned 0. Expected 1. |
| fastled_fixed_scale | 3 | `level` | `level + (if fixed_mode { 1 } else { 0 })` | scale_channel(128, 1, true) returned 0. Expected 1. |
| fastled_fixed_scale | 4 | `fraction` | `fraction + (if fixed_mode { 1 } else { 0 })` | Passed every withheld case |
| fastled_fixed_scale | 5 | `256` | `256 - (if fixed_mode { 1 } else { 0 })` | scale_channel(128, 1, true) returned 0. Expected 1. |
| fastled_fixed_scale | 6 | `product` | `fraction + product` | scale_channel(128, 1, true) returned 0. Expected 1. |
| go_footer_year_end | — | — | — | Empty menu |
