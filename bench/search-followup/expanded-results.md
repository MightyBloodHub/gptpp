# Portable search with a 152,192-operation allowance

This supplemental control was frozen before the new native solver was scored. One portable candidate search per task feeds three publication policies. The actual shared expressions were rendered, type-checked and independently scored in GPT++, typed Python and Rust.

| Policy | Correct / 12 in GPT++ | Typed Python | Rust | Published | Published wrong |
|---|---:|---:|---:|---:|---:|
| first | 0 | 0 | 0 | 6 | 6 |
| conservative | 0 | 0 | 0 | 0 | 0 |
| minimum | 0 | 0 | 0 | 5 | 5 |

| Task | First | Consensus | Minimum | Roots | Minimum cost | Distinct minimum behaviors | Intermediate work | Search s |
|---|---|---|---|---:|---:|---:|---:|---:|
| makeBricks | wrong | — | wrong | 70 | 11 | 1 | 152,192 | 5.024 |
| loneSum | — | — | — | 0 | None | 0 | 152,192 | 6.085 |
| luckySum | — | — | — | 0 | None | 0 | 152,192 | 5.921 |
| noTeenSum | — | — | — | 0 | None | 0 | 152,192 | 5.497 |
| roundSum | — | — | — | 0 | None | 0 | 152,192 | 5.362 |
| closeFar | wrong | — | — | 172 | 28 | 6 | 152,192 | 4.874 |
| blackjack | wrong | — | wrong | 3 | 25 | 1 | 152,192 | 2.424 |
| evenlySpaced | — | — | — | 0 | None | 0 | 152,192 | 4.885 |
| cigarParty | wrong | — | wrong | 51 | 10 | 1 | 152,192 | 1.577 |
| dateFashion | wrong | — | wrong | 5 | 25 | 1 | 152,192 | 2.225 |
| caughtSpeeding | wrong | — | wrong | 3 | 25 | 1 | 152,192 | 1.640 |
| sortaSum | — | — | — | 0 | None | 0 | 152,192 | 2.326 |

Across all twelve tasks, this search used 1,826,304 intermediate operations and 47.840 seconds. There were 0 wall-time expirations. These are algorithm-specific vector and partition operations. Matching ceilings does not give the algorithms identical grammars, runtimes or probes. [Secondary protocol](expanded-protocol.md) · [Native and smaller-control results](results.md) · [Raw archive](expanded.jsonl)
