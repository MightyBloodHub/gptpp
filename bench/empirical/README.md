# Scalar authoring pilot

The pilot measures whether a model needs fewer tokens and less time to deliver a correct scalar function in GPT++ than in typed Python or Rust. It compares the current GPT++ bootstrap with the standard type checker and execution workflow for each baseline. The experimental unit is a task family.

The 19 November 2026 run completed all 72 trials. Its report includes the acceptance rates, token and latency comparisons, and an offline replay that tested the effect of supplying a missing `!{}` annotation. [Results](results/2026-11-19.md) · [Raw data](results/2026-11-19.jsonl)

## Design

Two locally installed models, DeepSeek Coder 6.7B and Llama 3 8B, each solve the same six synthesis and six maintenance tasks in all three languages. The 72-cell matrix uses one seed per model and task. Language order is shuffled within a task, and task order is shuffled within a model. Both models use temperature zero, a 2,048-token context, and up to 240 new tokens per call. The log records model digests and runtime versions.

Each trial receives a task description, a function signature, a brief language guide and public examples. On maintenance tasks the model also receives the existing function. The model may replace that function once after a failed public check. Public feedback contains the first diagnostic or mismatch. The scorer runs the held-out cases only when public checks pass and excludes their output from every model prompt. Both the initial and the repaired function face the same acceptance requirement.

The corpus contains 36 public and 347 held-out cases. A separate oracle supplies each expected value. The preflight executes every reference against its oracle and verifies that each maintenance starter still fails the new requirement. The scorer checks Python with strict mypy and Rust with overflow checks enabled. GPT++ uses its checked scalar interpreter.

The evaluator uses scratch directories, a reduced environment and macOS sandbox profiles. Before a run it checks that the worker denies network access, reads of the project and writes outside its scratch directory. Processes have CPU, elapsed time, output and descriptor limits. These controls cover this local pilot. Qualification requires a disposable worker with an enforceable memory limit.

## Measurements

The JSONL records every completed trial, prompt, model output, token count, public feedback, hidden acceptance and elapsed time. Ollama supplies model-specific input and output token counts. Time includes model calls and public tool feedback. Model load and held-out evaluation times are recorded separately. GPT++ launches the interpreter once per case, while Rust and Python batch cases. Timing describes these concrete adapters, including that overhead. [Ollama generation API](https://docs.ollama.com/api/generate)

Report acceptance before and after the public repair and compute tokens and seconds per accepted trial across all assigned trials, including failures. The analysis pairs the same model and task across languages and resamples whole task families to estimate uncertainty. Tokens and elapsed seconds are separate measures of computational effort. The 20% target and two-point acceptance margin in the design plan describe later qualification. This pilot has 12 task families, two local models and one seed per condition.

## Reproduce

Use a macOS host with the two model digests recorded in the data, Ollama serving locally, Rust 1.97.1 and Python 3.11. Install the Python baseline tools in a virtual environment and run from the project root.

```sh
cargo build --locked --offline
python3 -m venv target/empirical-venv
target/empirical-venv/bin/python -m pip install mypy==1.15.0 mypy-extensions==1.2.0 typing-extensions==4.16.0
PYTHONDONTWRITEBYTECODE=1 target/empirical-venv/bin/python bench/empirical/run.py target/scalar-pilot.jsonl
python3 bench/empirical/summarize.py target/scalar-pilot.jsonl
python3 -B bench/empirical/replay_effects.py target/scalar-pilot.jsonl
```

Use a fresh output path for a new study. Reusing the path resumes completed cells only when the manifest matches. Keep the corpus and checked-in results out of any future qualification set.
