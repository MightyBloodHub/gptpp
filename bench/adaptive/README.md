# Adaptive caller context on maintenance tasks

**The adaptive GPT++ workflow was 53.4% below Rust's observed tokens per accepted edit, and 83.8% above typed Python's.** It accepted 2/8 at 2,955.50 tokens per accepted edit. Rust accepted 1/8 at 6,346 and Python accepted 3/8 at 1,608. The eight-task sample left the upper cost-ratio bound unbounded against Rust. GPT++ accepted one fewer change than Python. [Paired results and historical analysis](results/adaptive.md)

The previous multi-caller benchmark found that GPT++ accepted four of eight changes both with and without caller excerpts. Supplying the excerpts on every call raised token use. This follow-up starts with the target function and public examples, then exposes bounded caller excerpts only if the first failed public case invokes another function. The scope, target signature and caller code are fixed across all attempts. [Previous results](../maintenance/results/maintenance.md) · [Frozen procedure](protocol.md)

The study includes eight fresh single-module reproductions based on published rules. The tasks supply the target location and describe the required change. Each target has at least two unchanged consumers. Acceptance requires passing the checker and independent public and withheld cases. A withheld failure ends the trial and supplies no prompt feedback. The model gets at most one public-feedback retry.

Typed Python and Rust use the same adaptive rule. Two additional GPT++ arms use target-only and always-context prompts. All five conditions use the same local model, budgets, task order policy and caller selection criteria. The primary metric is total input and output tokens per accepted edit, including all failed attempts and retries. Local elapsed time describes each language's benchmark harness. The data cover one model, one seed and a small corpus of scalar repairs. [Raw trials](results/adaptive.jsonl)

GPT++ escalated five of its six retries to caller context. None of the five passed. Adaptive GPT++ used 13.9% more tokens than the target-only control. Both received identical first replies and accepted the same two changes. Compared with receiving context on every call, adaptive GPT++ used 17.0% fewer tokens. Both accepted two changes, on different tasks. Every successful edit across the five arms came on the first attempt.

Calibration checked 465 reference outputs. Offline replay reproduced all 70 model-attempt outcomes, including caller-failure attribution and all 10 withheld verdicts. Independently tokenizing the exact model input reproduced all 70 input counts. [Replay verifier](verify_adaptive.py)

GPT++ exposes the editing policy through `--caller-context-on-failure`. Supply `--cases` with public examples. A case can name a caller by setting `function`. The first failed behavioral case determines whether the retry gets caller excerpts. [Editor usage](../../tools/README.md)

## Reproduce

The runner uses the pinned local Qwen2.5-Coder 7B model, macOS evaluation sandbox, Python environment and compiler described in the preceding benchmark. The JSONL holds the exact prompts, responses and outcomes. An interrupted run resumes only with the same compiler and source manifest. [Environment setup](../maintenance/README.md)

```sh
target/empirical-venv/bin/python -B bench/adaptive/run_adaptive.py --calibrate
target/empirical-venv/bin/python -B bench/adaptive/run_adaptive.py target/adaptive-new.jsonl
python3 -B bench/adaptive/report_adaptive.py target/adaptive-new.jsonl
```

Analyze and replay the archived results without a model request.

```sh
python3 -B bench/adaptive/report_adaptive.py bench/adaptive/results/adaptive.jsonl
target/empirical-venv/bin/python -B bench/adaptive/verify_adaptive.py --replay bench/adaptive/results/adaptive.jsonl
```
