# Caller context after a failed public test

Run one local model on eight fresh application maintenance tasks. Each task changes the body or returned expression of a known shared function. The edit scope excludes signatures and every caller. Check the old and corrected programs in GPT++, strict typed Python and Rust before inference. Each withheld suite checks both the requested change and preserved behavior via multiple unchanged callers.

## Prompt policies

Give each arm the target declaration and old implementation, the same task and public test cases, and one fill-in-the-middle gap. A target-only prompt includes public call examples, including named callers, and omits caller source excerpts. Use Qwen2.5-Coder 7B. The same native grammar hints, stop sequences, budgets and caller selection algorithm used in the prior maintenance study apply here.

- `gpp_adaptive`, `python_adaptive`, and `rust_adaptive` start target-only. Expose bounded caller excerpts on the single retry only when the first failed public case calls a named function other than the target.
- `gpp_target` receives the same failure diagnostic and retries with target-only context.
- `gpp_context` receives the same caller excerpts on both calls, including the initial call.

Classify the first failing public case in fixture order. A type, compile or edit-boundary error has no failing entry. If a batch runtime error or malformed output cannot be attributed, run public cases individually until the first wrong result or runtime fault identifies its entry. The ordinary pass/mismatch path uses the batched evaluator. A caller wrong result or runtime fault can trigger context. A direct-target failure, static error, or failure with no identified entry leaves the adaptive prompt target-only. Exhaustion or success ends the public attempt. Check withheld tests only after a public pass, with no model feedback or retry from withheld outcomes.

## Analysis

Use seed 42 and temperature 0 initially and seed 43 and temperature 0.25 on retry, with 2,048 context tokens and at most 240 generated tokens per call. Randomize task and within-task arm order with seed 12713. Freeze sources, compiler and task hashes before the first completion. Preserve raw prompts, model responses, stop settings, per-attempt trigger and failure entry, calibrated reference results and timings. Rescore the archived candidates without additional model calls.

The primary comparator is typed Python with the same adaptive policy. Compare to Rust under that same policy. Compare adaptive GPT++ to its target-only and always-context controls. Score every assigned task and count every actual model token, including unsuccessful calls and retries. Report tokens per accepted edit, acceptance, the number of retries that showed context, on-retry acceptances, and each point estimate's distance to the goal. The 95% task-cluster interval for acceptance must start at no worse than −2 percentage points, and the ratio of tokens per accepted edit must end at 0.80 or lower. Keep local wall time separate. This eight-task sample fixes the target location and uses one model and seed.
