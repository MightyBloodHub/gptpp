# GPT++ roadmap

GPT++ is a working scalar compiler and an experiment in reducing the cost of correct software changes. The project measures all model tokens spent per edit that passes independent behavior tests. [Project overview](README.md) · [Detailed design](docs/design.md)

## Available today

- A parser and type checker, a reference interpreter, and an LLVM native backend for a single-module profile with checked scalar arithmetic. [Scalar language guide](docs/scalar-language.md) · [Grammar](spec/grammar.ebnf)
- Compiler-checked edits to entire functions or individual expressions. Editors can list the exact source ranges against a revision, preview a replacement, and apply it with a stale-source guard. Surrounding bytes and operator grouping are preserved. [Expression editor](docs/scalar-language.md#preview-an-edit-inside-a-function)
- Local-model proposals with public example checks. The maintenance preset starts with the target and can add caller excerpts after a failing public caller test. The experimental catalog method exposes each expression as a numbered choice and checks a single structured model response. [Authoring tools](tools/README.md)
- Matched benchmarks in GPT++, typed Python and Rust, with historical sources, raw model responses and replay programs. [Study index](bench/README.md)

## What the expression milestone established

The earlier Godot trial motivated editing a single expression inside a function. The compiler now supports that operation, including nested conditions, repeated expressions and revision-bound positions. The v9 study tested it on three new historical changes in Redis, FastLED and Go. Free-text selection produced zero accepted GPT++ repairs with either model. Supplying the correct location let StarCoder2 repair Redis for 908 tokens per accepted edit across the three tasks. Rust repaired the same case for 897 tokens per accepted edit. [Expression results](bench/expression/README.md) · [Historical tasks](bench/expression/sources.md)

The numbered catalog then produced valid selections on all 18 follow-up calls across the three languages. None of the edits passed the full behavior checks. The next development cycle will measure whether information from executing the public examples helps the model choose a useful site and compute the intended value. [Catalog results](bench/expression/results/catalog.md)

## Next milestone — Use failing examples to guide the edit

1. **Localize the discrepancy.** Run the starter on passing and failing public examples and record which expressions executed, their types, and their observed values. Try giving the model a short ranked list with those observations. Count the tokens needed for that evidence and the time spent collecting it.
2. **Constrain replacement generation.** Expose in-scope values and the selected expression's expected type. Test stopping at the end of one valid expression. Measure invalid fragments, well-typed behavior failures, successful repairs and complete workflow cost separately.
3. **Test on new project families.** First isolate each change on development data, including its Python and Rust equivalents and a one-shot body baseline. Freeze the best baseline and retry policy before running a disjoint, larger study. Keep a supplied-location control and measure localization cost when the model must choose.

## Evidence gates

Measure input and output tokens per accepted change, including all failed attempts and retries. Report first-attempt acceptance, acceptance within the full budget, and tool time separately. Report the ratio as unestimable if either workflow has zero accepted edits.

The proposed 20% claim requires both a paired 95% upper cost-ratio bound of **0.80 or lower** and a paired 95% lower acceptance-difference bound of **−2 percentage points or higher** against the comparator chosen before qualification. Check that the findings hold across task families and more than one model configuration. Compiler release quality has its own conformance and reliability criteria. [Decision thresholds](docs/design.md#197-proposed-gono-go-thresholds) · [Release criteria](docs/design.md#26-definition-of-done)

## Later milestones

| Milestone | Scope and exit criteria |
|---|---|
| Extend the executable profile | Add aggregates, explicit error values and initial collections in small increments. Keep interpreter and native behavior in agreement before building larger programs on them. |
| Support practical multi-module maintenance | Add modules, generated interfaces and a small standard library. Demonstrate a checked edit in a real multi-module program with caller regression tests and revision guards. |
| Qualify and harden releases | Broaden conformance and platform testing, assemble a disjoint benchmark suite, and publish supported profiles and measured limits. |

Self-hosting, a custom tokenizer and dedicated model training are optional research tracks. The detailed design records the dependencies and criteria for wider platform, runtime and library support. [Implementation phases](docs/design.md#20-implementation-roadmap)
