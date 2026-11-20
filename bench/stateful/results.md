# State-transition maintenance across three languages

Two pinned local models each attempted four previously unseen changes in each language. Public checks constrained the generated expression. Independent history-based oracles then tested the full end state on each withheld event sequence.

| Model | Language | First accepted | Final accepted | Calls | Input | Output | Tokens/accept | Model s | Tool/overhead s | Workflow s |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| qwen2.5-coder:7b | gpp | 2/4 | 2/4 | 6 | 2,192 | 77 | 1,134.5 | 13.36 | 0.95 | 14.30 |
| qwen2.5-coder:7b | rust | 2/4 | 2/4 | 6 | 2,376 | 87 | 1,231.5 | 10.84 | 6.51 | 17.36 |
| qwen2.5-coder:7b | python | 2/4 | 2/4 | 6 | 2,271 | 73 | 1,172.0 | 9.28 | 4.80 | 14.08 |
| starcoder2:3b | gpp | 0/4 | 0/4 | 8 | 3,234 | 124 | undefined | 6.80 | 0.00 | 6.81 |
| starcoder2:3b | rust | 0/4 | 0/4 | 8 | 3,538 | 84 | undefined | 4.51 | 0.01 | 4.52 |
| starcoder2:3b | python | 0/4 | 0/4 | 8 | 3,226 | 124 | undefined | 5.06 | 0.00 | 5.07 |

| Family | GPT++ | Rust | Typed Python | Shared grammar (GPT++/Rust/Python) | GPT++ automatic |
|---|---:|---:|---:|---|---|
| reading_marker | 1/2 | 1/2 | 1/2 | pass/pass/pass | pass |
| pair_dispatch | 0/2 | 0/2 | 0/2 | pass/pass/pass | pass |
| run_record | 1/2 | 1/2 | 1/2 | fail/fail/fail | incomplete |
| armed_toggle | 0/2 | 0/2 | 0/2 | pass/pass/pass | rejected |

Shared task, public-contract and oracle design took 173.764 seconds of AI-agent wall time from initial design to freeze. This shared cost was incurred once. Human labor and language-specific specification-authoring time were unmeasured. There were zero external clarifications; each automatic retry used only a type error or visible failing sequence. Model and validation time exclude subsequent withheld scoring. Local typechecking and compilation tools differ, so these workflow times include their actual adapter costs.

The shared controller, constraints and public information are matched across native languages. The model-free control removes inference and fixes candidate ordering. The GPT++ automatic column measures its separate built-in search and ambiguity policy. Four task families and two models are insufficient to establish a general language advantage. These programs keep their state in memory; the study does not measure distributed updates or multi-module integration.
