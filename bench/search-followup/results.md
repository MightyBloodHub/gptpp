# Minimum-cost selection on twelve externally specified exercises

The primary outcome is a native expression that the solver actually published and that passed all withheld inputs. Twelve CodingBat exercises contribute 288 public cases and 22,675 independently scored withheld inputs. The two preceding internal corpora did not include these exercises. Every starter failed its public checks. All 36 native reference implementations passed. One published closeFar example lies outside the finite scoring grid and remains an additional public check. [Task selection and budgets](protocol.md) · [External problem sources](sources.md)

| Selector | Correct / 12 | Published | Published wrong | Ambiguous | Search seconds |
|---|---:|---:|---:|---:|---:|
| Previous GPT++ | 0 | 0 | 0 | 0 | 0.602 |
| Default GPT++ | 0 | 0 | 0 | 0 | 0.714 |
| Minimum-cost GPT++ | 0 | 0 | 0 | 0 | 0.679 |
| Portable first pass | 0 | 3 | 3 | n/a | 5.070 |
| Portable consensus | 0 | 0 | 0 | 3 | 5.070 |
| Portable minimum cost | 0 | 0 | 0 | 3 | 5.070 |

Each portable row reports one common candidate search. The same candidates were rendered and run in GPT++, typed Python and Rust, yielding identical acceptance in all three. The portable policies chose among at most 256 public-fitting roots. The built-in compiler checked at most 256 submitted roots; each system also performed additional intermediate evaluations. Search timings are one host observation and exclude independent withheld scoring. The portable row times also exclude final native validation, which is recorded by backend in the archive.

| Task | Previous | Default | Minimum cost | Portable first | Portable consensus | Portable minimum | Withheld |
|---|---|---|---|---|---|---|---:|
| makeBricks | rejected | incomplete | incomplete | wrong | — | — | 976 |
| loneSum | rejected | incomplete | incomplete | — | — | — | 488 |
| luckySum | rejected | incomplete | incomplete | — | — | — | 976 |
| noTeenSum | rejected | incomplete | incomplete | — | — | — | 3,351 |
| roundSum | rejected | incomplete | incomplete | — | — | — | 10,624 |
| closeFar | rejected | incomplete | incomplete | wrong | — | — | 2,174 |
| blackjack | rejected | incomplete | incomplete | — | — | — | 876 |
| evenlySpaced | rejected | incomplete | incomplete | — | — | — | 2,173 |
| cigarParty | rejected | rejected | rejected | — | — | — | 88 |
| dateFashion | rejected | incomplete | incomplete | wrong | — | — | 97 |
| caughtSpeeding | rejected | incomplete | incomplete | — | — | — | 92 |
| sortaSum | rejected | incomplete | incomplete | — | — | — | 760 |

## Paired decisions

| Minimum-cost GPT++ compared with | Wins | Losses | Both correct | Both failed |
|---|---:|---:|---:|---:|
| Previous GPT++ | 0 | 0 | 0 | 12 |
| Default GPT++ | 0 | 0 | 0 | 12 |
| Portable first pass | 0 | 0 | 0 | 12 |
| Portable consensus | 0 | 0 | 0 | 12 |
| Portable minimum cost | 0 | 0 | 0 | 12 |

Minimum-cost GPT++ did not meet the preregistered criterion of higher independent acceptance than both its default policy and portable minimum-cost search on this block.

A cheaper public fit can be wrong on held-out values. A solver can also ask a question about a disagreement outside a task’s measured domain. Cost and ambiguity describe the sampled search space; they do not prove behavioral correctness.

## Fresh local model generation

| Model | Language | Correct / 12 | Passed public | Calls | Input tokens | Output tokens | Inference s | Public validation s |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| qwen2.5-coder:7b | gpp | 2 | 2 | 12 | 5,896 | 594 | 48.81 | 0.66 |
| qwen2.5-coder:7b | rust | 5 | 5 | 12 | 5,896 | 652 | 50.79 | 14.79 |
| qwen2.5-coder:7b | python | 1 | 1 | 12 | 5,634 | 518 | 48.85 | 8.70 |
| starcoder2:3b | gpp | 0 | 0 | 12 | 6,245 | 171 | 13.52 | 0.13 |
| starcoder2:3b | rust | 0 | 0 | 12 | 6,233 | 154 | 13.37 | 4.76 |
| starcoder2:3b | python | 0 | 0 | 12 | 5,862 | 147 | 14.31 | 4.56 |

Each task and language received one call per model. All 72 attempts count, with zero retries and zero external clarifications. GPT++ expressions were checked using the original shipped manual-fill interface. Native Python and Rust used the same public/withheld cases. Public problems may have appeared in model training. The study did not measure training contamination or human authoring time.

| Task | Qwen GPT++ | Qwen Python | Qwen Rust | StarCoder2 GPT++ | StarCoder2 Python | StarCoder2 Rust |
|---|---|---|---|---|---|---|
| makeBricks | failed public/type gate | failed public/type gate | failed public/type gate | failed public/type gate | failed public/type gate | failed public/type gate |
| loneSum | failed public/type gate | failed public/type gate | failed public/type gate | failed public/type gate | failed public/type gate | failed public/type gate |
| luckySum | failed public/type gate | failed public/type gate | failed public/type gate | failed public/type gate | failed public/type gate | failed public/type gate |
| noTeenSum | failed public/type gate | failed public/type gate | correct | failed public/type gate | failed public/type gate | failed public/type gate |
| roundSum | failed public/type gate | failed public/type gate | correct | failed public/type gate | failed public/type gate | failed public/type gate |
| closeFar | failed public/type gate | failed public/type gate | failed public/type gate | failed public/type gate | failed public/type gate | failed public/type gate |
| blackjack | failed public/type gate | failed public/type gate | failed public/type gate | failed public/type gate | failed public/type gate | failed public/type gate |
| evenlySpaced | failed public/type gate | failed public/type gate | failed public/type gate | failed public/type gate | failed public/type gate | failed public/type gate |
| cigarParty | correct | failed public/type gate | correct | failed public/type gate | failed public/type gate | failed public/type gate |
| dateFashion | failed public/type gate | failed public/type gate | correct | failed public/type gate | failed public/type gate | failed public/type gate |
| caughtSpeeding | correct | failed public/type gate | failed public/type gate | failed public/type gate | failed public/type gate | failed public/type gate |
| sortaSum | failed public/type gate | correct | correct | failed public/type gate | failed public/type gate | failed public/type gate |

## Search effort

| Task | Minimum GPT++ candidates | Public contract executions for guidance | Guidance value vectors | Minimum-mode value vectors | Numeric hypotheses | Portable value vectors | Portable branch comparisons | Portable public-fitting roots |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| makeBricks | 256 | 48 | 17,190 | 96,135 | 270 | 13,510 | 48,000 | 7 |
| loneSum | 256 | 156 | 19,984 | 96,018 | 405 | 13,500 | 48,000 | 0 |
| luckySum | 256 | 183 | 16,791 | 96,107 | 405 | 13,500 | 40,200 | 0 |
| noTeenSum | 256 | 181 | 17,850 | 96,105 | 405 | 13,500 | 39,000 | 0 |
| roundSum | 256 | 202 | 15,448 | 96,111 | 405 | 13,500 | 48,000 | 0 |
| closeFar | 256 | 48 | 20,012 | 95,949 | 282 | 13,506 | 47,700 | 2 |
| blackjack | 256 | 164 | 6,898 | 95,437 | 138 | 13,500 | 2,400 | 0 |
| evenlySpaced | 256 | 48 | 19,916 | 95,951 | 270 | 13,500 | 48,000 | 0 |
| cigarParty | 217 | 48 | 2,326 | 95,038 | 2 | 13,500 | 48,000 | 0 |
| dateFashion | 256 | 150 | 9,158 | 95,458 | 138 | 13,521 | 48,000 | 8 |
| caughtSpeeding | 256 | 144 | 2,326 | 95,033 | 3 | 13,500 | 48,000 | 0 |
| sortaSum | 256 | 193 | 9,713 | 95,253 | 138 | 13,500 | 23,400 | 0 |

The larger portable control separately spent 152,192 operations per task. Its first-pass and minimum selectors published six and five wrong expressions respectively. [Larger portable results](expanded-results.md)

Work counters are specific to each implementation. All three portable policies reuse the same search. Exact proposals, compiler reports and score digests are in the [trial archive](results.jsonl). [Reproduction guide](README.md)
