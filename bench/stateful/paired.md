# Comparing the language under a shared edit interface

Each paired assignment is one model working on the same change in both languages. There are four task families and two models. A win means GPT++ alone passed the visible contracts and withheld sequence tests. A loss means the comparator alone passed. A tie includes both passing and both failing.

| Comparator | GPT++ wins | GPT++ losses | Both pass | Both fail |
|---|---:|---:|---:|---:|
| rust | 0 | 0 | 2 | 6 |
| python | 0 | 0 | 2 | 6 |

| Language | Accepted | Total model tokens | Tokens per accepted change |
|---|---:|---:|---:|
| gpp | 2/8 | 5,627 | 2,813.5 |
| rust | 2/8 | 6,085 | 3,042.5 |
| python | 2/8 | 5,694 | 2,847.0 |

Token totals pool the two pinned model configurations and charge failed trials and retries. The per-model results report each tokenizer separately. All programs used the same typed expression slot and behavior checks. Differences in syntax, model familiarity, compiler interfaces and validation time are still combined within each native arm. The comparison does not establish a language-wide advantage.
