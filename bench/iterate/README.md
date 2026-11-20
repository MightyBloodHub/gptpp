# Can GPT++ make a correct edit cheaper?

The original 72-trial pilot accepted zero GPT++ submissions. These experiments change how the model writes a function and measure every attempt against typed Python and Rust. An accepted trial must pass static checks, all public examples and a separate set of withheld cases. [Original pilot](../empirical/results/2026-11-19.md)

Across three fresh comparisons, 160 trials covered 24 distinct scalar tasks and three local models. The first comparison improved GPT++ acceptance against its own whole-function workflow. In the final eight-task comparison, stopped native GPT++ accepted 1/8 at 4,481 tokens per accepted edit, typed Python accepted 4/8 at 765, and Rust accepted 3/8 at 1,003. The same stop rule benefited Rust substantially. These results support keeping the checked editor and measuring any further savings against equally equipped baselines. [Final paired report](results/boundary.md)

## From failures to a working editor

Of 48 earlier GPT++ model calls, 20 used compound assignment. The compiler now supports checked compound assignments and lazy conditional values. Rechecking the 24 terminal GPT++ submissions from the original pilot with this compiler accepted one unchanged function. Recovering the exact function body and supplying the declaration increased the number that compiled from eight to eleven. It recovered no further correct solutions. This replay made zero model calls and used the original expected results. [Replay with outcomes per submission](results/v1-replay.json)

The next prototype supplied the declaration and asked for one expression or a function body. Two development rounds reused four old tasks and two models. Both accepted 0/8. After the first round the repair prompt named failing arguments and the second call used a new seed and temperature. The development rounds consumed 32 model calls and 12,704 tokens combined, reported separately from the fresh comparisons. [Initial development calls](results/development.jsonl) · [Revised repair calls](results/development-repair.jsonl)

## Matched comparisons

The first study assigned DeepSeek Coder 6.7B and Llama 3 8B to eight fresh tasks in four conditions. The revised GPT++ fragment workflow accepted 4/16 at 2,361 tokens per accepted trial. The same compiler with whole-function prompting accepted 1/16 at 19,744 tokens per accepted trial. Python fragments accepted 8/16 at 711 and Rust fragments accepted 4/16 at 2,040. Of the twelve final GPT++ fragment failures, nine returned a wrong answer and three failed to check. The difference against whole-function generation includes the scope, prompt, feedback and repair sampling. [Protocol](protocol.md) · [Paired report](results/paired.md) · [Raw prompts, outputs and judgments](results/paired.jsonl)

The second study used Qwen2.5-Coder 7B on eight additional tasks. The model received both sides of a source gap for native infill. A same-model GPT++ chat condition controlled for the choice of generation interface. An exploratory condition accepted restricted Python syntax as input and translated it to checked GPT++ source. The Python and Rust comparators received the same scope and native infill budget. Python infill was the preselected external comparator. [Infill protocol](infill-protocol.md) · [Replication report](results/infill.md) · [Raw prompts, outputs and judgments](results/infill.jsonl)

Python infill accepted 4/8 at 871 tokens per accepted change. GPT++ chat accepted 1/8. Native GPT++ infill, the original translated workflow and Rust infill each accepted 0/8. All eight Rust terminal answers crossed the edit boundary, as did four native GPT++ terminal answers. Several completions contained a function closer followed by tests or another function. These outcomes motivated a prospective test of stopping generation at the boundary. The open and stopped conditions in that test retain the same structural validation. [Boundary-stop protocol](boundary-protocol.md)

The model also wrote the correct nearest-station calculation with `abs` in both Python and translated GPT++. The original translator rejected the call. We added checked integer `abs`, `min` and `max` to the proposal tool and replayed the terminal responses for both conditions. The extension accepted 2/8 archived Python completions, up from 1/8, and 1/8 archived translated completions, up from 0/8. Both gains came from the same task. A correct Python loop and a float-to-int calculation remained outside the supported subset. This retrospective replay holds the generated text fixed. It cannot measure what a new model call would cost. [Projection replay](results/projection-replay.json)

The final study assigned seven workflows to each of eight additional tasks. Stopping at the function boundary reduced GPT++ input plus generated tokens from 5,242 to 4,481 (14.5%) with the same single accepted task. Rust acceptance rose from 1/8 to 3/8 with fewer tokens. Typed Python accepted 4/8 in both modes. The exploratory translated workflow accepted 1/8 at 4,272 tokens per accepted edit. Against stopped Python, native GPT++ had a −37.5 percentage-point acceptance difference (95% paired interval −87.5 to +12.5) and used 5.86 times as many tokens per accepted edit. With only one GPT++ success, many bootstrap draws have no accepted GPT++ work, leaving the cost ratio without a finite upper bound. [Full comparison](results/boundary.md) · [Raw boundary-stop data](results/boundary.jsonl)

Pricing input and output differently would not reverse that observed comparison under uniform rates on the same model. Per accepted edit, stopped GPT++ consumed 3,624 input and 857 output tokens. Python used 624.5 input and 140.75 output. Applying any common nonnegative input and output rates, with at least one positive rate, gives a GPT++/Python token-charge ratio between 5.80 and 6.09 on this sample. Tiered cache pricing, human review and host compute would require additional measurements.

## Reading the measurements

Each fresh corpus contains two tasks in each combination of synthesis or maintenance and an expression or body edit. The first corpus has 24 public and 182 hidden cases. The second has 24 public and 206 hidden cases. Before inference, references in all three languages ran against the same expected outputs. The runners also checked that each maintenance starter failed the new behavior. The comparison allows one initial call and one public-feedback repair, with up to 240 generated tokens per call. A public pass ends inference, including when the submission later fails hidden tests.

The boundary-stop follow-up has 24 public and 183 hidden cases on eight further tasks. Each target language has a matched open/stopped pair on the same model and prompts. The seventh condition uses stopped Python syntax translated to checked GPT++ with the added scalar operations. All runs used one Apple M1 Pro host. The model budget is the same across conditions. [Frozen boundary-stop design](boundary-protocol.md)

The three scored runs made 285 model calls using 98,838 tokens. Independent replay reproduced every public verdict and every triggered hidden verdict. For the 98 boundary-stop calls, independently tokenizing the exact rendered Qwen prompts also reproduced every reported input count. The raw log records generated-token counts from the server, including stop tokens removed from the visible completion. The verifier can check an independently supplied tokenizer against its pinned fingerprint. [Replay verification](verify.py) · [Boundary-stop verification](verify_boundary.py)

Tokens per accepted trial divides **all input and generated tokens**, including failed trials and retries, by the number of accepted trials in the condition. Ollama 0.6.2 counts the rendered input, including cached context, and decoded output steps, including any terminating token. Time for the authoring workflow includes the local model call, model loading within that call and the public checks. The raw logs also record time for final hidden scoring. GPT++ starts an interpreter process for each case. Python and Rust batch the cases. Training, model download, study development, human review and financial pricing are outside these measurements. [Ollama 0.6.2 token accounting](https://github.com/ollama/ollama/blob/v0.6.2/runner/llamarunner/runner.go)

Each report includes first-pass and final acceptance, all tokens, time, incremental repair cost and paired uncertainty. The 95% intervals resample whole tasks, keeping model observations together. A zero-acceptance arm can leave a ratio undefined. With eight selected scalar tasks per study, these data support engineering decisions. Financial or general-language qualification requires an explicit cost model, more independent tasks, additional models and realistic project changes. [Frozen study protocol](protocol.md)

## Reproduce

Use the macOS worker, Rust/LLVM setup and Python 3.11 environment specified in the initial pilot. For inference use Ollama 0.6.2 serving locally, with the exact models and digests recorded in each JSONL manifest. The replication needs only the Qwen model. A new output path starts a run. An interrupted run can resume from its last completed trial when its manifest matches. The verification script also checks the transitive task-helper dependency used by the replication. [Environment setup](../empirical/README.md)

```sh
cargo build --locked --offline
target/empirical-venv/bin/python -B bench/iterate/run_study.py target/paired-new.jsonl
target/empirical-venv/bin/python -B bench/iterate/run_infill.py target/infill-new.jsonl
target/empirical-venv/bin/python -B bench/iterate/run_boundary.py target/boundary-new.jsonl
```

The checked-in results can be analyzed without inference. Integrity and behavioral replay use the recorded environment and compiler binary. The reports themselves require only Python's standard library.

```sh
python3 -B bench/iterate/report.py bench/iterate/results/paired.jsonl
python3 -B bench/iterate/report.py bench/iterate/results/infill.jsonl
python3 -B bench/iterate/report_boundary.py bench/iterate/results/boundary.jsonl
target/empirical-venv/bin/python -B bench/iterate/verify.py --replay bench/iterate/results/paired.jsonl bench/iterate/results/infill.jsonl
target/empirical-venv/bin/python -B bench/iterate/verify_boundary.py --replay bench/iterate/results/boundary.jsonl
target/empirical-venv/bin/python -B bench/iterate/replay_v1.py --output target/v1-replay.json
target/empirical-venv/bin/python -B bench/iterate/replay_projection.py --output target/projection-replay.json
```
