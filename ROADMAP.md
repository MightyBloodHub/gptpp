# GPT++ roadmap

GPT++ is a programming language designed for agents that write and maintain software. An agent should be able to ask which code ran, what it can change there, and which input would distinguish two proposed behaviors. The project measures whether these operations lead to correct changes and what each one costs. [Project overview](README.md) · [Detailed design](docs/design.md)

## Available today

- A parser and type checker, a reference interpreter, and an LLVM native backend for a single-module profile with checked scalar arithmetic. [Scalar language guide](docs/scalar-language.md) · [Grammar](spec/grammar.ebnf)
- Compiler-checked edits to entire functions or individual expressions. Editors can list the exact source ranges against a revision, preview a replacement, and apply it with a stale-source guard. Surrounding bytes and operator grouping are preserved. [Expression editor](docs/scalar-language.md#preview-an-edit-inside-a-function)
- Typed execution traces and example-guided repair. Agents can query an expression's observed inputs, result and fault through a caller, then search a bounded grammar for replacements that pass public examples. When candidates disagree, an agent can request a concrete input to clarify the desired behavior. [Trace reference](docs/scalar-language.md#trace-a-call) · [Repair guide](tools/README.md#search-for-an-edit-with-public-examples)
- Local-model proposals with public example checks. The maintenance preset starts with the target and can add caller excerpts after a failing public caller test. The experimental catalog method exposes each expression as a numbered choice and checks a single structured model response. [Authoring tools](tools/README.md)
- Matched benchmarks in GPT++, typed Python and Rust, with historical sources, raw model responses and replay programs. [Study index](bench/README.md)

## What the expression milestone established

The earlier Godot trial motivated editing a single expression inside a function. The compiler now supports that operation, including nested conditions, repeated expressions and revision-bound positions. The v9 study tested it on three new historical changes in Redis, FastLED and Go. Free-text selection produced zero accepted GPT++ repairs with either model. Supplying the correct location let StarCoder2 repair Redis for 908 tokens per accepted edit across the three tasks. Rust repaired the same case for 897 tokens per accepted edit. [Expression results](bench/expression/README.md) · [Historical tasks](bench/expression/sources.md)

The numbered catalog then produced valid selections on all 18 follow-up calls across the three languages. None of the edits passed the full behavior checks. [Catalog results](bench/expression/results/catalog.md)

## What execution contributed

Running the public examples yields exact expressions and visible bindings for a bounded search. On the same three development tasks, Qwen2.5-Coder 7B and StarCoder2 3B each selected a valid Redis repair. The deterministic first candidate produced the same result. FastLED had six public-passing choices, including one correct fix, and both models abstained. The Go calendar change exceeded what the search found. [Paired results and timing](bench/expression/results/repair.md) · [Audit of every candidate](bench/expression/results/repair-menu.md)

A separate follow-up asked for two expected FastLED outputs from a reference calculation. Those answers narrowed six choices to the one that passed all 14 withheld checks. The workflow also accepted Redis and returned no Go candidate. It made 912 candidate executions across the three tasks. [Distinguishing inputs, answers and outcomes](bench/expression/results/distinguish.md)

## Next milestone

1. **Test distinguishing inputs on new specifications.** Measure how many additional expected results it takes to distinguish otherwise plausible edits. Charge separately for obtaining that answer from a human, a specification or a reference program. Record cases where all candidates are wrong or none of the available inputs distinguishes them.
2. **Test transfer.** Freeze the search grammar, type information, budgets and public-example policy. Run on new project families and give Python and Rust comparable tracing, search and edit controls. Include a no-model selection baseline and record tool time alongside inference cost.
3. **Extend the language past scalar edits.** Introduce structured values or explicit errors with machine-readable types and trace observations. Demonstrate a caller-sensitive edit on that feature with interpreter and native conformance.

## Evidence for efficiency claims

Measure input and output tokens per accepted change, including all failed attempts and retries. Report first-attempt acceptance, acceptance within the full budget, and tool time separately. Report the ratio as unestimable if either workflow has zero accepted edits.

The historical 20% target qualifies a specific comparative cost claim. It sets no threshold for implementing a useful language operation. That claim requires both a paired 95% upper cost-ratio bound of **0.80 or lower** and a paired 95% lower acceptance-difference bound of **−2 percentage points or higher** against the comparator chosen before qualification. Check that the findings hold across task families and more than one model configuration. Compiler release quality has its own conformance and reliability criteria. [Decision thresholds](docs/design.md#197-proposed-gono-go-thresholds) · [Release criteria](docs/design.md#26-definition-of-done)

## Later milestones

| Milestone | Scope and exit criteria |
|---|---|
| Extend the executable profile | Add aggregates, explicit error values and initial collections in small increments. Keep interpreter and native behavior in agreement before building larger programs on them. |
| Support practical multi-module maintenance | Add modules, generated interfaces and a small standard library. Demonstrate a checked edit in a real multi-module program with caller regression tests and revision guards. |
| Qualify and harden releases | Broaden conformance and platform testing, assemble a disjoint benchmark suite, and publish supported profiles and measured limits. |

Self-hosting, a custom tokenizer and dedicated model training are optional research tracks. The detailed design records the dependencies and criteria for wider platform, runtime and library support. [Implementation phases](docs/design.md#20-implementation-roadmap)
