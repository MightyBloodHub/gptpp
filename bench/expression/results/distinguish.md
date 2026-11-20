# Choosing edits with distinguishing examples

A separate, oracle-assisted follow-up used each distinct task menu from the model study. The CLI received a fixed pool of fresh, unlabeled target inputs for each task. It asked for a label only when candidate predictions disagreed. This follow-up made zero model calls.

| Task | Menu size | Unlabeled inputs supplied | Extra oracle labels | Surviving IDs | Selected ID | Withheld result |
|---|---:|---:|---:|---|---:|---|
| redis_lru_timestamp | 2 | 24 | 0 | 1, 2 | 1 | accepted |
| fastled_fixed_scale | 6 | 96 | 2 | 4 | 4 | accepted |
| go_footer_year_end | 0 | 16 | 0 | — | — | empty_menu |

The tool asked for `scale_channel(11, 151, true)`. The independent specification oracle returned **6**. The predicted groups were 7 for IDs [1, 3, 6], 6 for IDs [2, 4, 5].

The tool asked for `scale_channel(11, 23, true)`. The independent specification oracle returned **1**. The predicted groups were 0 for IDs [2, 5], 1 for IDs [4].

With 2 additional oracle labels, the chosen patches passed all withheld cases on 2/3 development tasks. The CLI executed 912 candidate/probe pairs in 6.31 seconds. The study scored only the final choices. Agreement on a finite pool leaves open the possibility of a difference on another input. Resolving a disagreement requires a reliable answer source. An empty menu leaves no edit to select. The earlier model-only outcomes remain a separate measurement.
