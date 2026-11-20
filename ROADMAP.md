# GPT++ roadmap

GPT++ is a working scalar compiler and an experiment in reducing the cost of correct software changes. The next milestone focuses on changing a small part of an existing function and measuring the effect on accepted edits. [Project overview](README.md) · [Detailed design](docs/design.md)

## Available today

- A parser and type checker, a reference interpreter, and an LLVM native backend for a single-module profile with checked scalar arithmetic. [Scalar language guide](docs/scalar-language.md) · [Grammar](spec/grammar.ebnf)
- Revision-guarded function edits, previews, public example checks and a local-model proposal tool. The maintenance preset starts with the target and can retry once after a failed caller check. [Editing guide](tools/README.md)
- Paired authoring benchmarks with published protocols, completions and replay tools. The upstream transfer study found a 0.09% cost difference between the cheapest observed Qwen GPT++ and typed Python workflows, each with one accepted change on a different task. The 20% target remains open. [Maintenance evidence](bench/policy/README.md)

## Next milestone — Edit one existing expression

In the Godot transfer case, a whole-body GPT++ rewrite kept the inclusive comparison responsible for the defect. A scoped operation would let the model edit the comparison directly. The current `gpp edit --expr` operation replaces a function body with a return expression. This milestone introduces selection of a single existing expression inside that body. [Upstream cases](bench/policy/upstream-sources.md) · [Transfer results](bench/policy/results/transfer.md)

1. **Build a compiler-checked edit.** Identify an expression in a specific source revision, preview the replacement, and type-check the edited module before applying it. Confirm byte preservation outside the selected span and cover stale revisions, ambiguous targets, type errors and caller regressions. Expression addressing and the CLI syntax are open design decisions.
2. **Compare equivalent workflows.** Give GPT++, typed Python and Rust the same expression-level edit scope, public feedback, model settings and resource budgets. Include the existing whole-body workflow as a control. Record first-attempt results separately from workflows that can retry.
3. **Test transfer on fresh changes.** Use unseen project families with independently checked acceptance tests and identifiable callers. Freeze the task set, strongest comparator and analysis before qualification. Publish all attempts, failure categories, replay inputs and any limits of extracted tasks. [Evaluation protocol](docs/design.md#19-evaluation-and-success-criteria)

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
