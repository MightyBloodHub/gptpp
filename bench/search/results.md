# Bounded completion on nine fresh task families

The primary endpoint counts a task only when the solver publishes a typed expression and every withheld check agrees. Nine families include four history-dependent transitions. The corpus contains 156 public input/output pairs, 1,774 withheld direct calls and 12,125 withheld event histories. A single incorrect outcome fails the entire task.

| Solver | Correct / 9 | Published | Published wrong | Ambiguous | Search wall, total |
|---|---:|---:|---:|---:|---:|
| Previous GPT++ | 1 | 2 | 1 | 0 | 0.423 s |
| New GPT++, grammar only | 0 | 1 | 1 | 1 | 0.831 s |
| New GPT++, default | 1 | 2 | 1 | 5 | 0.181 s |
| Portable search, first passing | 4 | 8 | 4 | n/a | 2.594 s |
| Portable search, probe consensus | 0 | 0 | 0 | 8 | 2.594 s |

The portable search ran once per task and its selected abstract expressions were independently rendered, type-checked and executed by all three backends. Its two rows share the same search work. Search times are single-host, one run per solver and family. Native CLI times include internal public verification. The portable row times cover enumeration and internal public evaluation. Its separate backend validation costs are in the archive.

| Family | Previous | New grammar | New default | Portable first | Portable consensus | Direct withheld | Histories |
|---|---|---|---|---|---|---:|---:|
| drum_index | rejected | incomplete | incomplete | correct | — | 32 | 1,089 |
| bit_packet | rejected | incomplete | correct | correct | — | 112 | 124 |
| fan_memory | wrong | wrong | wrong | wrong | — | 12 | 5,456 |
| camera_follow | rejected | incomplete | ambiguous | — | — | 125 | 5,456 |
| time_intersection | rejected | incomplete | ambiguous | wrong | — | 607 | 0 |
| sensor_vote | rejected | incomplete | ambiguous | wrong | — | 325 | 0 |
| meeting_quorum | rejected | incomplete | ambiguous | wrong | — | 172 | 0 |
| parcel_pick | correct | ambiguous | ambiguous | correct | — | 238 | 0 |
| tile_color | rejected | incomplete | incomplete | correct | — | 151 | 0 |

## Paired outcomes and advisory candidates

- Against previous compiler, the default compiler had 1 win, 1 loss and 7 ties.
- Against new grammar only, the default compiler had 1 win, 0 losses and 8 ties.
- Against portable first passing, the default compiler had 0 wins, 3 losses and 6 ties.
- Against portable probe consensus, the default compiler had 1 win, 0 losses and 8 ties.

| Solver | First public-passing expression correct, out of 9 |
|---|---:|
| Previous GPT++ | 1 |
| New GPT++, grammar only | 1 |
| New GPT++, default | 2 |

The advisory row scores the first candidate passing public checks even if the actual solver asked a question. It gives no credit in the primary endpoint. A single public gate can fit multiple expressions. On the fan task, even the deliberately defective starter passed every sampled public example while failing held-out behavior. That family remains in every denominator.

## Matched local model generation

| Model | Language | Correct / 9 | Passed public | Calls | Input | Output | Model seconds | Public validation seconds |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| qwen2.5-coder:7b | gpp | 3 | 5 | 9 | 3,405 | 232 | 28.95 | 0.52 |
| qwen2.5-coder:7b | rust | 4 | 5 | 9 | 3,405 | 191 | 21.13 | 8.56 |
| qwen2.5-coder:7b | python | 4 | 5 | 9 | 3,217 | 171 | 19.05 | 6.81 |
| starcoder2:3b | gpp | 0 | 1 | 9 | 3,640 | 117 | 10.04 | 0.06 |
| starcoder2:3b | rust | 0 | 1 | 9 | 3,631 | 84 | 7.49 | 0.68 |
| starcoder2:3b | python | 0 | 1 | 9 | 3,361 | 95 | 7.23 | 2.02 |

One model call per task and language, with identical sampling settings and a native syntax card. There were no retries or external clarifications. Withheld checks followed the public gate. Payloads, including failed replies, are in the archive. The GPT++ model arm used the previous shipped type checker and manual hole-fill path. The matched model arms measure single-expression generation independently of automatic search.

## Search work

| Family | Previous tested | New grammar tested | Hybrid tested | Portable intermediate vector evaluations | Portable branch tests | Portable root candidates |
|---|---:|---:|---:|---:|---:|---:|
| drum_index | 90 | 256 | 256 | 13,828 | 34,200 | 32 |
| bit_packet | 63 | 256 | 256 | 13,821 | 43,200 | 58 |
| fan_memory | 28 | 217 | 217 | 14,838 | 45,600 | 4 |
| camera_follow | 90 | 256 | 130 | 13,500 | 48,000 | 0 |
| time_intersection | 170 | 256 | 130 | 14,940 | 48,000 | 256 |
| sensor_vote | 154 | 256 | 131 | 13,980 | 48,000 | 186 |
| meeting_quorum | 62 | 256 | 133 | 14,226 | 45,600 | 14 |
| parcel_pick | 90 | 14 | 14 | 14,940 | 48,000 | 129 |
| tile_color | 62 | 256 | 256 | 13,993 | 48,000 | 87 |

All search arms had a 256 completed-candidate ceiling and a 30-second deadline. The portable solver uses public examples to prune intermediate values, compare branch partitions, and identify public-fitting root expressions. It checks many more intermediate vectors than the number of roots. The new native compiler also uses internal evaluations to construct candidates. The counters reflect different units of work and should be read with the wall-time measurements. See the raw native reports for the compiler guidance counters.

| Native guidance work | Total across nine tasks |
|---|---:|
| contract_runs | 599 |
| examples | 126 |
| value_vectors | 83,374 |
| branch_joins | 486 |
| proposals | 66 |

The native CLI and portable solver timings were recorded while the independent local model collection was finishing on the same host. Host load was uncontrolled. The archive records separate public validation time for each native rendering.

The corpus covers small scalar rules and four bounded event folds. The public labels and complete reference behavior represent shared specification effort. No human authoring time was measured. The finite cases and repeated model calls do not constitute evidence about general-purpose software maintenance. [Frozen protocol](protocol.md) · [Full replay instructions and provenance](README.md)
