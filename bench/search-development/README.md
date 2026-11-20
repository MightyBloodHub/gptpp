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

## Minimum-cost mode on the published nine-task corpus

These nine tasks had already been published when the minimum-cost engine was developed. At 256 candidates, the frozen build selected four expressions. All four passed every withheld direct call and event history. The other five returned concrete ambiguity reports. [Replay archive](minimum.json) · [Original benchmark](../search/README.md)

| Selected task | Withheld direct calls | Withheld histories | Wrong outcomes |
| --- | ---: | ---: | ---: |
| Drum index | 32 | 1,089 | 0 |
| Bit packet | 112 | 124 | 0 |
| Camera follow | 125 | 5,456 | 0 |
| Parcel pick | 238 | 0 | 0 |

Fan memory, time intersection, sensor vote, meeting quorum and tile color were ambiguous. Reproduce with `python3 -B bench/search-development/minimum.py` after building commit `eaac2cd`. The replay checks each published expression with the original independent scorer and stores all nine reports with `--write`.

## Piecewise search on the two earlier corpora

Both corpora were available to the authors when they designed piecewise search. These development replays measure whether it handles previously observed failures. The compiler used its original 256-candidate limit and 10,000-assignment verification budget. A selected edit had to pass the public checks and every withheld case in its original scorer. [External twelve reports](piecewise-external-twelve.json) · [Original nine reports](piecewise-original-nine.json)

| Development corpus | Minimum correct | Piecewise correct | Piecewise wrong | Ambiguous | Incomplete |
| --- | ---: | ---: | ---: | ---: | ---: |
| Twelve external scalar exercises | 0 / 12 | 2 / 12 | 0 | 3 | 7 |
| Original nine scalar and stateful tasks | 4 / 9 | 4 / 9 | 0 | 5 | 0 |

On the twelve exercises, the compiler selected a blackjack expression that chooses the largest eligible total and a cigarParty expression that accounts for weekdays and weekends. They passed all 876 and 88 withheld calls respectively. The compiler found conflicting public fits for dateFashion, caughtSpeeding and sortaSum. It exhausted the candidate budget on the seven remaining tasks. The four successes on the original nine were drum index, bit packet, camera follow and parcel pick. [Original twelve-task results](../search-followup/results.md)

Build compiler commit `2f24b54` in release mode and run both replays from the repository root. The runner validates full compiler reports, independent scores and input hashes against the archived results.

```sh
cargo build --release --locked --offline
python3 -B bench/search-development/piecewise.py external-twelve
python3 -B bench/search-development/piecewise.py original-nine
```
