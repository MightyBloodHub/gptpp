# Matched-helper sensitivity

The primary GPT++ prompt advertises `abs(x)` while its sketch omits that declaration. Typed Python and Rust already expose it. This supplemental comparison gives GPT++ the helper in every public search, candidate check, calibration and sealed evaluation. The implementation returns `-x` for negative inputs and `x` otherwise, with ordinary GPT++ checked-I64 overflow. The nonnegative return for `I64::MIN` is unrepresentable. The original public bounds use small integers. Search may discover other candidates when it sees the helper. The primary run and its interpretation remain separately identifiable.

Run from the repository root after all 90 primary decisions close. Supply a new output directory.

```sh
python3 -B bench/checked_edits/matched_helpers.py run bench/checked_edits/run target/matched-helpers
```

The supplemental transport checks the primary model digest, compiler digest, source freeze and trial roster. It replays a metered model receipt at most once, and only for the same full JSON request and assignment (task, language and arm, or the named preparation audit). It charges the receipt’s original tokens and elapsed inference time. A request without an identical receipt triggers a live call to the pinned Qwen model. It records the original receipt line or the new physical usage. The six preparation audit prompts follow the same rule and their proposed mutations are checked again. Reference/mutant calibration, public checking and scoring run locally again. Standalone costs include the primary specification-preparation interval of 167 seconds, current validation work, and all attributed audit and trial model costs. The report separates physical and attributed inference including preparation. Supplemental implementation time and author tokens are unmetered.

This uses the original assignments, budgets, repair rules, scoring and analysis. A separate process first opens the sealed evaluator after the sensitivity ledger closes and has no route back into a trial. The comparison diagnoses the helper mismatch. The families have already been commissioned and cannot supply a second fresh qualification. [Primary protocol](protocol.md)

Collector SHA-256 `179ff3ecfc784b538896cfb1e53dc701babd8187709c89a779f74dc184519b83`. Each sensitivity manifest also pins the helper text, this policy, the primary source freeze and the closed primary decisions.
