# Where the maintenance attempts failed

Qwen2.5-Coder 7B accepted **26 of 64 edits** across the GPT++ and Python arms of the v5 and v6 maintenance studies. Of the 38 terminal failures, **36 produced a checkable program that returned a wrong value**. I reviewed the final completion in each cell, its first failing public or withheld example, and the task specification. The unit here is an assigned task and arm. The 64 cells cover 16 task families, each tried four ways. The counts include the v5 Python-to-GPT++ projection. [v5 raw attempts](../maintenance/results/maintenance.jsonl) · [v6 raw attempts](../adaptive/results/adaptive.jsonl)

| Primary failure in terminal completion | v5 | v6 | Evidence in the code |
|---|---:|---:|---|
| Missing or incorrect decision branch, priority or fallback | 7 | 18 | v5 substitution cap (3) and byte ranges (4). v6 Git push (4), modal ties (4), settlement (4), WCAG levels (3), gallery orientation (1), UTF-16 ranges (2). |
| Incorrect arithmetic or cyclic mapping | 7 | 4 | v5 weekday offset (3), PCM quantization (1), DNS serial arithmetic (3). All four v6 transit attempts reduced the newly permitted hour modulo 24. |
| Rejected before behavioral evaluation | 1 | 1 | The projected restart-backoff body initialized `seconds` inside branches, outside its later scope. The target-only WCAG body omitted a return semicolon. |

Three counterexamples explain the distinction. The v5 substitution bodies returned zero whenever `used >= 3`, even with the five-player option active and two players still available. In v6 the adaptive GPT++ UTF-16 body checked `scalar >= 65536` inside an outer branch requiring `scalar <= 65535`, making its two-unit result unreachable. The transit candidates extended validation through hour 47 but still wrapped midnight. For a 24:10 departure with the reference clock at minute 1435, the caller returned zero minutes to wait instead of 15. Each cell received one primary classification at the first observed failure. A parse rejection can conceal additional semantic errors.

## Tokens and repairs

| Study and arm (8 tasks each) | First-pass accepts | Accepted on retry / retries | Input tokens | Output tokens | Tokens spent on retries |
|---|---:|---:|---:|---:|---:|
| v5 GPT++ with callers | 3 | 1 / 5 | 6,536 | 864 | 3,245 |
| v5 GPT++ target only | 3 | 1 / 5 | 4,483 | 819 | 2,366 |
| v5 GPT++ from Python syntax | 3 | 0 / 5 | 6,644 | 754 | 3,221 |
| v5 typed Python | 6 | 0 / 2 | 4,100 | 462 | 1,002 |
| v6 GPT++ adaptive | 2 | 0 / 6 | 5,349 | 562 | 3,158 |
| v6 GPT++ target only | 2 | 0 / 6 | 4,629 | 561 | 2,437 |
| v6 GPT++ with callers | 2 | 0 / 6 | 6,584 | 539 | 3,221 |
| v6 typed Python adaptive | 3 | 0 / 5 | 4,351 | 473 | 2,404 |

Prompts consumed **42,676 of 47,710 tokens (89.4%)**. The 40 repairs used 19,214 input and 1,840 output tokens, **44.1% of all tokens**, and added two accepts. Both were in v5. One replaced Rust-style `let mut` with GPT++ `var`. The other corrected the negative weekday formula. **23 of 40 retries reproduced the first response byte for byte.**

One v5 byte-range retry passed the public case by changing the output for both zero and oversized suffix lengths together. The withheld case `first_byte(0, 0, true)` then returned 0 where −1 was required. A repair that silences one failure can still break a preservation case. [v5 verification](../maintenance/verify.py) · [v6 verification](../adaptive/verify_adaptive.py)

An ordered list of conditions and results can expose mutually exclusive cases and make a fallback explicit. The evidence motivates testing that representation with a compact prompt. It cannot establish that the model will supply every condition or compute the correct result. The native loop in the backoff task also shows a limit of a loop-free policy surface. The studies used one model and seed, related arms share tasks, and the failure labels are retrospective. Accepted changes per token on fresh tasks remain the test.
