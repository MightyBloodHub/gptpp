# GPT++ roadmap

GPT++ is a programming language designed for agents that write and maintain software. An agent should be able to ask which code ran, what it can change there, and which input would distinguish two proposed behaviors. The project measures whether these operations lead to correct changes and what each one costs. [Project overview](README.md) · [Detailed design](docs/design.md)

## Available today

- Typed expression holes, context queries and contract-checked completion. The compiler completed the reservation component’s repeated-cancel outcome and identified a concrete question when two inventory expressions disagreed. [Run both sketches](examples/reservations/README.md#complete-a-typed-decision)
- Records and enums carry state and domain errors across checked function calls. GPT++ compiles the component into a shared library with a versioned scalar C ABI. A persistent Python CLI and an independent Rust client call the same library. [Reservation application](examples/reservations/README.md)
- Optional symbolic verification with Z3 for supported straight-line code, branches and inlined calls. The reservation module’s eight contracts include full-width cancellation properties. The browser runs the finite verifier on the same working module. [Proof obligations](examples/reservations/cancellation.proof.gpp.inc) · [Browser verifier](https://gptpp.sandoog.co/#finite-contracts)

- Named finite contracts and a bounded verifier. A contract declares the integer or Boolean inputs it covers. The compiler evaluates its predicate for each assignment, reports a counterexample when the property fails and distinguishes complete checks from exhausted budgets. The edit tool can use the same contracts while searching for one replacement expression. [Finite contract walkthrough](docs/scalar-language.md#verify-a-finite-contract) · [Contract-guided editing](tools/README.md#repair-an-expression-against-source-contracts)
- A parser and type checker, a reference interpreter, and an LLVM native backend for a single-module profile with records, enums and checked scalar arithmetic. [Scalar language guide](docs/scalar-language.md) · [Grammar](spec/grammar.ebnf)
- Native scalar operations for rounding, bounds and predicates. An agent can write `(elapsed != 0) as I64` to obtain 0 or 1, nest checked integer `min` and `max` calls, or express a closed bound as `clamp(value, low, high)`. The interpreter and native backend implement the same semantics. [Scalar language reference](docs/scalar-language.md)
- Persistent compiler evaluation through `gpp probe`. The repair tools can check many independent edits and run their example cases using one open compiler process. Across six repair searches and three distinguishing-input searches, the sum of median command times fell from 28.143 to 1.334 seconds on the test host. Both versions returned identical menus and questions. [Authoring tools](tools/README.md) · [Timing study](bench/expression/results/probe.md)
- Compiler-checked edits to entire functions or individual expressions. Editors can list the exact source ranges against a revision, preview a replacement, and apply it with a stale-source guard. Surrounding bytes and operator grouping are preserved. [Expression editor](docs/scalar-language.md#preview-an-edit-inside-a-function)
- Typed execution traces and example-guided repair. Agents can query an expression's observed inputs, result and fault through a caller, then search a bounded grammar for replacements that pass public examples. When candidates disagree, an agent can request a concrete input to clarify the desired behavior. [Trace reference](docs/scalar-language.md#trace-a-call) · [Repair guide](tools/README.md#search-for-an-edit-with-public-examples)
- Local-model proposals with public example checks. The maintenance preset starts with the target and can add caller excerpts after a failing public caller test. The experimental catalog method exposes each expression as a numbered choice and checks a single structured model response. [Authoring tools](tools/README.md)
- Matched benchmarks in GPT++, typed Python and Rust, with historical sources, raw model responses and replay programs. [Study index](bench/README.md)

## Fresh stateful edits

Two models attempted four state-machine changes in GPT++, typed Python and Rust. Each language repaired the same two of eight assignments. All six accepted edits came from Qwen’s first attempts. StarCoder2 repaired none. The study charged failed attempts to each language and recorded 42 model calls across 24 assignments. Holding the grammar and candidate ordering fixed, no-model search solved three of four tasks in every language. GPT++’s built-in completion solved two of four. Qwen supplied a streak update missed by both searches. [Results and costs](bench/stateful/results.md) · [Frozen evaluation](bench/stateful/protocol.md)

## What finite contracts added

Two public examples per task admitted all ten hand-authored expression edits in a three-task development study. The complete predicates covered 73 tuples and rejected six of those edits. For signed carry, two edits agreed on the entire declared domain. A capped implementation failed three of five additional inputs outside it. The repair menu retained the ambiguity. In a separate search on the same tasks, the first contract-verified edit passed all three domains and the first example-only edit passed two. The search grammars and their ordering differed. No model made a selection. In a separate six-assignment run on those tasks, Qwen repaired capacity and StarCoder2 returned no accepted edit. [Model-generated edits](bench/contracts/model-results.md) [Frozen protocol](bench/contracts/protocol.md) · [Results and limitations](bench/contracts/results.md)

## What changed when the compiler learned the missing operations

Two models attempted three new scalar contracts in each of GPT++, typed Python and Rust. In the original runs, Qwen solved two Python tasks and one Rust task. The GPT++ compiler rejected expressions that used `as I64` and ordinary integer bounds operations. The language now implements those forms. Keeping all the saved replies and their original token charges, Qwen GPT++ went from zero of three accepted changes to three of three. Its three patches passed 36 withheld checks and 879 additional direct inputs. StarCoder2 accepted none, and neither model repaired the older Redis, FastLED or Go extracts with these saved expressions. [Original matched results](bench/expression/results/fresh-agent.md) · [Retrospective replay](bench/expression/results/compat.md)

## What the expression milestone established

The earlier Godot trial motivated editing a single expression inside a function. The compiler now supports that operation, including nested conditions, repeated expressions and revision-bound positions. The v9 study tested it on three new historical changes in Redis, FastLED and Go. Free-text selection produced zero accepted GPT++ repairs with either model. Supplying the correct location let StarCoder2 repair Redis for 908 tokens per accepted edit across the three tasks. Rust repaired the same case for 897 tokens per accepted edit. [Expression results](bench/expression/README.md) · [Historical tasks](bench/expression/sources.md)

The numbered catalog then produced valid selections on all 18 follow-up calls across the three languages. None of the edits passed the full behavior checks. [Catalog results](bench/expression/results/catalog.md)

## What execution contributed

Running the public examples yields exact expressions and visible bindings for a bounded search. On the same three development tasks, Qwen2.5-Coder 7B and StarCoder2 3B each selected a valid Redis repair. The deterministic first candidate produced the same result. FastLED had six public-passing choices, including one correct fix, and both models abstained. The Go calendar change exceeded what the search found. [Paired results and timing](bench/expression/results/repair.md) · [Audit of every candidate](bench/expression/results/repair-menu.md)

A separate follow-up asked for two expected FastLED outputs from a reference calculation. Those answers narrowed six choices to the one that passed all 14 withheld checks. The workflow also accepted Redis and returned no Go candidate. It made 912 candidate executions across the three tasks. [Distinguishing inputs, answers and outcomes](bench/expression/results/distinguish.md)

## Current performance measurements

Persistent evaluation preserved every repair menu and distinguishing question across nine workloads and three repeated measurements. The sum of command medians fell from 28.143 to 1.334 seconds. Correct scalar executables used about 1.3 MiB peak resident memory and ran in about 7 ms on this host. Rust used about 1.5 MiB and 8 ms, while Python used about 11.6 MiB and 0.3 seconds. Native times include startup and are sensitive to scheduling. GPT++ native builds took about 0.25 seconds, compared with about 0.11 seconds for Rust. [Authoring latency](bench/expression/results/probe.md) · [Program measurements](bench/runtime/results.md)

## Next milestone

1. **Test distinguishing inputs on new specifications.** Measure how many additional expected results it takes to distinguish otherwise plausible edits. Charge separately for obtaining that answer from a human, a specification or a reference program. Record cases where all candidates are wrong or none of the available inputs distinguishes them.
2. **Test transfer.** Freeze the search grammar, type information, budgets and public-example policy. Run on new project families and give Python and Rust comparable tracing, search and edit controls. Include a no-model selection baseline and record tool time alongside inference cost.
3. **Reduce native build cost.** Profile tool discovery, LLVM optimization, C runtime compilation and linking against the measured Rust build times. Verify compiler output and fault behavior after every optimization.
4. **Extend structured program maintenance.** Test typed completion across independently versioned components, publish compatibility checks for native interfaces and measure when verifying a caller catches a callee edit that local examples miss.

## How we compare workflows

Compare GPT++ with typed Python and Rust on the same change requests, public feedback, budgets and withheld checks. Publish first-pass and final acceptance, input and output tokens, model calls and retries, tool time, and any additional answers supplied by people or reference programs. Report compiler throughput and program runtime separately, with the workloads and hardware used to measure them.

For cost per accepted change, count the resources spent on every assigned task and divide by the number accepted. Zero accepted changes leave this cost undefined. For a broader claim, fix the comparator before evaluation, use fresh task families and multiple models, and publish paired uncertainty estimates. Releases document which language operations work, where a comparator does better and which measures still need evidence. [Evidence for comparative claims](docs/design.md#197-evidence-for-comparative-claims) · [Release criteria](docs/design.md#26-definition-of-done)

## Later milestones

| Milestone | Scope and exit criteria |
|---|---|
| Extend the executable profile | Extend the existing records and enums with initial collection support in small increments. Keep interpreter and native behavior in agreement before building larger programs on them. |
| Support practical multi-module maintenance | Add modules, generated interfaces and a small standard library. Demonstrate a checked edit in a real multi-module program with caller regression tests and revision guards. |
| Qualify and harden releases | Broaden conformance and platform testing, assemble a disjoint benchmark suite, and publish supported profiles and measured limits. |

Self-hosting, a custom tokenizer and dedicated model training are optional research tracks. The detailed design records the dependencies and criteria for wider platform, runtime and library support. [Implementation phases](docs/design.md#20-implementation-roadmap)
