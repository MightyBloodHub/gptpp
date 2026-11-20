# Example-filtered GPT++ expression repairs

Each pinned model attempted the same three development tasks. A selected edit must pass all public and withheld checks. The first-candidate control applies menu item 1 without inference.

| Model | Task | Candidates tested | Menu size | Choice | Withheld outcome | First candidate |
|---|---|---:|---:|---:|---|---|
| qwen2.5-coder:7b | redis_lru_timestamp | 512 | 2 | 1 | accepted | accepted |
| qwen2.5-coder:7b | go_footer_year_end | 282 | 0 | — | no_candidates | no_candidates |
| qwen2.5-coder:7b | fastled_fixed_scale | 224 | 6 | — | abstained | heldout_wrong_answer |
| starcoder2:3b | redis_lru_timestamp | 512 | 2 | 1 | accepted | accepted |
| starcoder2:3b | go_footer_year_end | 282 | 0 | — | no_candidates | no_candidates |
| starcoder2:3b | fastled_fixed_scale | 224 | 6 | — | abstained | heldout_wrong_answer |

| Model | Workflow | Accepted | Model calls | Input tokens | Output tokens | Tokens/accept |
|---|---|---:|---:|---:|---:|---:|
| qwen2.5-coder:7b | Archived catalog | 0/3 | 3 | 1,367 | 140 | undefined |
| qwen2.5-coder:7b | Example-filtered menu | 1/3 | 2 | 869 | 16 | 885.0 |
| qwen2.5-coder:7b | First candidate | 1/3 | 0 | 0 | 0 | 0.0 |
| starcoder2:3b | Archived catalog | 0/3 | 3 | 1,432 | 74 | undefined |
| starcoder2:3b | Example-filtered menu | 1/3 | 2 | 907 | 18 | 925.0 |
| starcoder2:3b | First candidate | 1/3 | 0 | 0 | 0 | 0.0 |

Across 6 trials the search yielded 2 empty menus. The models abstained 2 times. Withheld checks refuted 0 selected edits that passed the public examples.

The repair CLI used 36.28 seconds across all trials, including 12.03 seconds in model generation requests. 2/6 searches reached the candidate budget before exhausting the grammar. Timing depends on the host and model cache. The scorer ran after each timed CLI invocation.

The three project extracts were previously used for development. The archived catalog generated its own replacement string. The new tool spends deterministic search time building the choices. Both models draw from the same menu for a given task. A language-wide cost advantage, the value of a model over deterministic ordering on new tasks, and performance against comparable Python or Rust search remain open.
