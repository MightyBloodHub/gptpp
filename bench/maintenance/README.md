# Multi-caller maintenance benchmark

**GPT++ missed the 20% token target against typed Python. It came within 7.1 percentage points of the target against Rust.** With matched caller context, GPT++ accepted 4/8 at 1,850 tokens per accepted edit, Python accepted 6/8 at 760.33, and Rust accepted 3/8 at 2,124.33. GPT++ was 2.43× as costly as Python and 12.9% cheaper than Rust by this measure. Matching the 20% point target at unchanged acceptance requires another 67.1% token reduction against Python or 8.1% against Rust. The small sample did not clear both thresholds against either comparator. [Full results and paired intervals](results/maintenance.md)

The benchmark tests edits to shared scalar functions with multiple application consumers. Four fixtures reproduce documented rule changes in USPS, Amazon S3, Kubernetes, and IFAB. Four others correct behavior against published contracts for calendar dates, PCM audio, DNS serial ordering, and HTTP ranges. The repository contains independently written reproductions with small application modules and regression suites. Each task preserves its caller code, and withheld tests check both updated and previously correct behavior through at least two callers.

GPT++ now offers `--caller-context` to show bounded excerpts of functions that use the target. Examples passed with `--cases` can name any checked function in the same module. An edit preview can therefore check the behavior that callers observe before publishing a patch. The benchmark uses the same caller selection algorithm in all three languages. It also tests native GPT++ with only the target supplied, and an exploratory projected input that generates restricted Python syntax and translates to checked GPT++. [Proposal usage](../../tools/README.md) · [Frozen protocol](protocol.md)

In the GPT++ control, removing caller excerpts left acceptance at 4/8 and reduced cost per accepted edit to 1,325.50 tokens. The two GPT++ arms accepted different sets of tasks. Caller excerpts remain opt-in, and caller assertions work independently of the prompt option.

Every condition gets the target location, current implementation, task text and public examples. The model fills an expression or body while the runner preserves the existing signatures and every caller. The model may repair one public failure. Passes are checked against withheld tests. An accepted edit passes both groups. The token count includes the full prompt and response for every failed attempt and retry. This is a development sample over one local model, measuring language and authoring workflow together. The files exercise multiple callers within one small module and start with the target already identified.

The eight tasks test 20 distinct caller functions. The 128 withheld cases include 69 caller assertions. Of those, 27 exercise the requested change and 42 check preserved behavior. The other 59 call the target directly. All three languages expose the same callers in the same order. GPT++ stops a test batch on the first wrong value and reruns that case for the diagnostic. Python and Rust collect the batch outputs before comparing them, so a later runtime fault can take precedence over a wrong value in their repair feedback. The report times the benchmark's language adapters and checking harness. [Recorded prompts and verdicts](results/maintenance.jsonl)

Preflight checked 468 reference outputs. Offline replay reproduced all 61 attempt outcomes, including all 22 triggered withheld evaluations. Independent tokenization reproduced every recorded input count. The evaluated output token counts come from Ollama. [Verifier](verify.py)

## Reproduce

The runner uses the macOS sandbox and the pinned toolchain and Python environment documented in the initial empirical pilot. Ollama requires the recorded Qwen2.5-Coder 7B digest. The JSONL records the model template, exact prompts, sampled replies, source hashes, evaluation and token counts. Resuming a run requires the same manifest. [Setup](../empirical/README.md)

```sh
cargo build --locked --offline
target/empirical-venv/bin/python -B bench/maintenance/run.py --calibrate
target/empirical-venv/bin/python -B bench/maintenance/run.py target/maintenance-new.jsonl
python3 -B bench/maintenance/report.py target/maintenance-new.jsonl
```

Analyze and verify the archived benchmark without calling the model.

```sh
python3 -B bench/maintenance/report.py bench/maintenance/results/maintenance.jsonl
target/empirical-venv/bin/python -B bench/maintenance/verify.py --replay bench/maintenance/results/maintenance.jsonl
```
