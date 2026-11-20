# Final confirmation on eleven external scalar exercises

Two contiguous eligible slices from CodingBat contributed 11 directly specified rules, 264 public examples and 2,342 independently checked withheld inputs. These tasks were frozen before inspecting the piecewise implementation. A correct publication passed every test in its native backend. The unit counted below is a whole exercise. Several exercises share mathematical structure. [Frozen selection and qualification rule](protocol.md) · [Public source exercises](sources.md)

| Automatic solver | Correct / 11 | Published | Published wrong | Ambiguous | Incomplete | Search seconds |
|---|---:|---:|---:|---:|---:|---:|
| previous | 0 | 0 | 0 | 0 | 0 | 0.390 |
| strict | 1 | 1 | 0 | 1 | 2 | 0.489 |
| minimum | 1 | 2 | 1 | 0 | 2 | 0.531 |
| piecewise | 4 | 7 | 3 | 2 | 1 | 1.053 |

| Portable search | Selector | Correct GPT++ / 11 | Typed Python | Rust | Published | Published wrong | Search seconds |
|---|---|---:|---:|---:|---:|---:|---:|
| compact | first | 1 | 1 | 1 | 4 | 3 | 2.509 |
| compact | conservative | 1 | 1 | 1 | 1 | 0 | 2.509 |
| compact | minimum | 1 | 1 | 1 | 1 | 0 | 2.509 |
| expanded | first | 2 | 2 | 2 | 8 | 6 | 20.366 |
| expanded | conservative | 1 | 1 | 1 | 2 | 1 | 20.366 |
| expanded | minimum | 2 | 2 | 2 | 4 | 2 | 20.366 |
| larger | first | 2 | 2 | 2 | 8 | 6 | 41.068 |
| larger | conservative | 0 | 0 | 0 | 0 | 0 | 41.068 |
| larger | minimum | 2 | 2 | 2 | 4 | 2 | 41.068 |

The compact portable beam and both larger cost-layered beams had the same cap of 256 fully submitted roots and the same 30-second deadline. The two cost-layered controls allow 152,192 and 302,192 intermediate operations. The three policies within each size share the same candidate search and elapsed time. Each selected result was separately rendered, statically checked and executed in its actual language. Public validation times are archived per backend.

| Native task | Previous | Strict hybrid | Minimum cost | Piecewise | Withheld |
|---|---|---|---|---|---:|
| love6 | rejected | incomplete | incomplete | incomplete | 552 |
| in1To10 | rejected | rejected | rejected | ambiguous | 46 |
| specialEleven | rejected | rejected | rejected | correct | 76 |
| more20 | rejected | rejected | rejected | rejected | 77 |
| old35 | rejected | rejected | rejected | ambiguous | 76 |
| sumDouble | rejected | correct | correct | correct | 417 |
| diff21 | rejected | rejected | rejected | correct | 61 |
| parrotTrouble | rejected | rejected | rejected | correct | 24 |
| makes10 | rejected | incomplete | incomplete | wrong | 552 |
| nearHundred | rejected | rejected | rejected | wrong | 147 |
| posNeg | rejected | ambiguous | wrong | wrong | 314 |

| Task | Compact first / consensus / minimum | Expanded first / consensus / minimum | Larger first / consensus / minimum |
|---|---|---|---|
| love6 | — / — / — | — / — / — | — / — / — |
| in1To10 | wrong / — / — | wrong / — / — | wrong / — / — |
| specialEleven | — / — / — | wrong / wrong / wrong | wrong / — / wrong |
| more20 | — / — / — | wrong / — / wrong | wrong / — / wrong |
| old35 | — / — / — | — / — / — | — / — / — |
| sumDouble | — / — / — | — / — / — | — / — / — |
| diff21 | — / — / — | correct / — / correct | correct / — / correct |
| parrotTrouble | correct / correct / correct | correct / correct / correct | correct / — / correct |
| makes10 | wrong / — / — | wrong / — / — | wrong / — / — |
| nearHundred | — / — / — | wrong / — / — | wrong / — / — |
| posNeg | wrong / — / — | wrong / — / — | wrong / — / — |

## Published piecewise expressions

| Exercise | Exact selected expression | Wrong withheld inputs | First disagreement |
|---|---|---:|---|
| specialEleven | `((n % 11) <= 1)` | 0 | — |
| sumDouble | `if (a != b) { (a + b) } else { (a * 4) }` | 0 | — |
| diff21 | `if (n <= 20) { ((-n) + 21) } else { ((n * 2) + -42) }` | 0 | — |
| parrotTrouble | `if (hour <= 6) { talking } else { (talking && (!(hour <= 20))) }` | 0 | — |
| makes10 | `(((b + a) == 10) \|\| (b == 10))` | 22 | [10, -5] expected True, returned False |
| nearHundred | `if (n <= 183) { ((n <= 102) && (!(n <= 89))) } else { (n <= 205) }` | 19 | [103] expected True, returned False |
| posNeg | `if negative { (a <= 0) } else { ((b * a) <= -1) }` | 55 | [-6, 0, True] expected False, returned True |

## Paired primary endpoint

| Piecewise compared with | Wins | Losses | Both correct | Both failed |
|---|---:|---:|---:|---:|
| previous | 4 | 0 | 0 | 7 |
| strict | 3 | 0 | 1 | 7 |
| minimum | 3 | 0 | 1 | 7 |
| compact first | 3 | 0 | 1 | 7 |
| compact conservative | 3 | 0 | 1 | 7 |
| compact minimum | 3 | 0 | 1 | 7 |
| expanded first | 2 | 0 | 2 | 7 |
| expanded conservative | 3 | 0 | 1 | 7 |
| expanded minimum | 2 | 0 | 2 | 7 |
| larger first | 2 | 0 | 2 | 7 |
| larger conservative | 4 | 0 | 0 | 7 |
| larger minimum | 2 | 0 | 2 | 7 |

The piecewise selector solved **4/11**, the preceding native minimum-cost mode solved **1/11** and the larger portable minimum-cost control solved **2/11**. The preregistered condition required greater acceptance than both earlier controls. The experiment **met** that condition. These counts concern eleven bounded exercises.

## Fresh one-call model generation

| Model | Language | Correct / 11 | Passed public | Calls | Input tokens | Output tokens | Model s | Public validation s |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| qwen2.5-coder:7b | gpp | 7 | 7 | 11 | 4,302 | 352 | 36.68 | 0.55 |
| qwen2.5-coder:7b | rust | 7 | 7 | 11 | 4,302 | 332 | 30.63 | 9.97 |
| qwen2.5-coder:7b | python | 7 | 8 | 11 | 4,110 | 342 | 30.83 | 9.70 |
| starcoder2:3b | gpp | 0 | 0 | 11 | 4,639 | 183 | 13.34 | 0.29 |
| starcoder2:3b | rust | 0 | 0 | 11 | 4,628 | 152 | 10.52 | 4.41 |
| starcoder2:3b | python | 0 | 0 | 11 | 4,334 | 162 | 10.25 | 3.38 |

| Task | Qwen GPT++ | Qwen Python | Qwen Rust | StarCoder2 GPT++ | StarCoder2 Python | StarCoder2 Rust |
|---|---|---|---|---|---|---|
| love6 | — | — | — | — | — | — |
| in1To10 | — | wrong | — | — | — | — |
| specialEleven | correct | correct | correct | — | — | — |
| more20 | correct | correct | correct | — | — | — |
| old35 | — | — | correct | — | — | — |
| sumDouble | correct | correct | correct | — | — | — |
| diff21 | correct | correct | correct | — | — | — |
| parrotTrouble | correct | correct | — | — | — | — |
| makes10 | correct | correct | correct | — | — | — |
| nearHundred | correct | correct | correct | — | — | — |
| posNeg | — | — | — | — | — | — |

A dash means the public or type gate withheld publication. “Wrong” means a published expression failed at least one withheld input. There were zero retries and zero external clarifications. English instructions were available to the models. Automatic solvers received the same labeled examples in the task module. The public external exercises may have appeared in model training.

## Actual intermediate search work

| Native mode | Root candidates tested | Guidance contract runs | Guidance vectors | Minimum-cost vectors | Numeric hypotheses | Additional piecewise counters |
|---|---:|---:|---:|---:|---:|---|
| previous | 478 | 0 | 0 | 0 | 0 | — |
| strict | 1,739 | 781 | 64,601 | 0 | 0 | — |
| minimum | 1,864 | 781 | 64,601 | 1,013,032 | 461 | — |
| piecewise | 2,088 | 781 | 64,601 | 1,013,032 | 461 | piecewise.residual_operations=109,965, piecewise.subset_operations=1,129,797 |

| Portable mode | Intermediate vector evaluations | Branch comparisons | Root checks | Wall timeouts |
|---|---:|---:|---:|---:|
| compact | 148,893 | 495,600 | 111 | 0 |
| expanded | 1,541,283 | 132,829 | 228 | 0 |
| larger | 3,082,391 | 241,721 | 348 | 0 |

Counters refer to different internal operations and are not instruction or CPU budgets. Native search timing includes the compiler's internal validation. Portable search timings cover candidate search, with separate public native validation in the archive. All wall-time observations are host- and load-dependent. Full per-task proposals and diagnostics are in the [raw archive](results.jsonl). [Offline reproduction](README.md)
