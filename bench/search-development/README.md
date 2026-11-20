# Historical completion replay

At a limit of 64 candidate programs, the updated compiler produced passing edits for three of four historical tasks. The previous release produced two. At the default limit of 256, the updated compiler produced two passing edits and the previous release produced one. Every returned edit passed all withheld histories for its task. [Per-run reports and withheld scores](results.json)

These four families were available during development. The comparison measures how the new search handles previously published successes and failures. It uses the same GPT++ source bytes, candidate limits, public contracts, assignment budget and hidden history scorer for each compiler. The baseline is commit `8359fc699e2d528ac01f82f802b236f18a063227`. The revised grammar and hybrid mode had identical outcomes in these runs. [Original corpus and protocol](../stateful/README.md)

| Task | Previous 64 | Grammar 64 | Hybrid 64 | Previous 256 | Grammar 256 | Hybrid 256 |
| --- | --- | --- | --- | --- | --- | --- |
| Reading marker | Pass | Ambiguous | Ambiguous | Ambiguous | Ambiguous | Ambiguous |
| Pair dispatch | Pass | Pass | Pass | Pass | Pass | Pass |
| Longest run | Incomplete | Pass | Pass | Rejected | Ambiguous | Ambiguous |
| Armed toggle | Rejected | Pass | Pass | Rejected | Pass | Pass |

A pass requires automatic selection, checked insertion of the chosen expression, and zero disagreements with the independent oracle on all event histories through length six excluded from the public examples. At 64 candidates the three selected edits passed 3,262 withheld histories. A rejected or incomplete search returns no edit. An ambiguous result includes two contract-passing programs that produce different outcomes on a direct call.

For the reading marker, both copying the current page and taking its remainder modulo four satisfy the visible cases. The new compiler asks about recalling a bookmark with the page and bookmark both at four. A user can reach this state by advancing four times and marking the current page. The two proposals return different bookmarks.

For the longest run, 64 candidates suffice to select `max(s.best, s.streak + 1)`. The wider search finds a second expression that also passes the public histories. Its direct-call witness has a running streak of one and a negative historical best. The published history oracle starts from zero and only records nonnegative values. This witness demonstrates a difference for a type-correct direct call outside that application's reachable states.

## Reproduce

From the repository root, use a checkout containing the baseline commit, the pinned Rust toolchain, and Python 3.

```sh
cargo build --locked --offline
python3 -B bench/search-development/replay.py
```

The runner builds the baseline from its pinned Git sources in a temporary directory, copies both executables, and runs all 24 task, search-mode and budget combinations. It uses an assignment budget of 10,000 per full verification. Use `--write` to regenerate the archive or `--baseline-gpp PATH` to use a previously built baseline. Each record includes the source digest, the compiler's completion report and the hidden score for any selected expression. Binaries from different debug build directories may have different digests.
