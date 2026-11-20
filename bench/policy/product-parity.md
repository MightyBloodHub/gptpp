# Replaying selected native arms through the product CLI

Archived responses were replayed through `tools/propose.py --maintenance` with a loopback Ollama stub and the real compiler. Qwen used full-body editing. StarCoder2 used `--prepend` and its raw FIM transport. The transfer replay also enabled `--caller-obligation`. The CLI received public cases only. A separate interpreter run evaluated withheld cases against its revision-checked preview.

| Study | Model | Trials | Calls | Archive accepted | CLI accepted | Terminal outcomes matched | Exact prompt and suffix | After AST normalization |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| v7 | qwen2.5-coder:7b | 8 | 8 | 5 | 5 | 8/8 | 4/8 | 8/8 |
| v7 | starcoder2:3b | 8 | 13 | 1 | 1 | 8/8 | 6/13 | 13/13 |
| v8 | qwen2.5-coder:7b | 3 | 5 | 1 | 1 | 3/3 | 2/5 | 5/5 |
| v8 | starcoder2:3b | 3 | 5 | 0 | 0 | 3/3 | 2/5 | 5/5 |

Exact prompt equality compares the prefix and suffix sent by the CLI to the saved study fields, including caller feedback on retries. The normalized comparison rerenders the study prompt with the compiler’s canonical GPT++ spelling, which expands compact blocks and spaces operators. The verified transport checks cover model, token limits, seeds, temperature, stop sequences, and raw versus templated FIM. Replaying fixed text measures patch and evaluator parity; new generations could change with prompt formatting.

Run `target/empirical-venv/bin/python -B bench/policy/replay_product.py` after building `gpp` and the [caller obligation analyzer](../../tools/caller_obligation.md). [v7 raw trials](results/policy.jsonl) · [v8 raw trials](results/transfer.jsonl)
