# GPT++
## A general-purpose programming language and compiler optimized for AI-authored software

**Document:** `docs/design.md`<br>
**Design revision:** 0.6<br>
**Date:** 21 November 2026<br>
**Status:** The scalar language has named finite contracts. An agent can check a Boolean predicate over a declared domain, inspect a concrete counterexample and verify a candidate edit against the same property. [Executable contract](../examples/capacity.gpp) · [Scalar language reference](scalar-language.md#verify-a-finite-contract)

> **Mission:** Give AI agents the language and compiler operations they need to construct, understand and revise correct programs. Compiled programs run independently of a model.

GPT++ is a working project name. It does not imply C++ compatibility, affiliation with a model vendor, or dependence on a particular model. Name, command, extension, and package-registry availability must be checked before public distribution.

---

## Contents

1. [Executive decision](#1-executive-decision)
2. [What AI efficiency actually means](#2-what-ai-efficiency-actually-means)
3. [Evidence, hypotheses, and corrections](#3-evidence-hypotheses-and-corrections)
4. [Product boundaries and initial users](#4-product-boundaries-and-initial-users)
5. [Architecture decisions](#5-architecture-decisions)
6. [Representations and canonical source](#6-representations-and-canonical-source)
7. [Language specification: proposed baseline](#7-language-specification-proposed-baseline)
8. [Examples of GPT++](#8-examples-of-gpt)
9. [Grammar and parsing strategy](#9-grammar-and-parsing-strategy)
10. [Compiler architecture](#10-compiler-architecture)
11. [Runtime, memory, and interoperability](#11-runtime-memory-and-interoperability)
12. [Standard library and packages](#12-standard-library-and-packages)
13. [The AI authoring protocol](#13-the-ai-authoring-protocol)
14. [Diagnostics and repair](#14-diagnostics-and-repair)
15. [Contracts, testing, and verification](#15-contracts-testing-and-verification)
16. [Security and execution policy](#16-security-and-execution-policy)
17. [Incremental builds and reproducibility](#17-incremental-builds-and-reproducibility)
18. [Model adaptation and training data](#18-model-adaptation-and-training-data)
19. [Evaluation and success criteria](#19-evaluation-and-success-criteria)
20. [Implementation roadmap](#20-implementation-roadmap)
21. [Repository and engineering workstreams](#21-repository-and-engineering-workstreams)
22. [Prioritized implementation backlog](#22-prioritized-implementation-backlog)
23. [Team, infrastructure, and cost model](#23-team-infrastructure-and-cost-model)
24. [Risks and decision gates](#24-risks-and-decision-gates)
25. [Versioning and governance](#25-versioning-and-governance)
26. [Definition of done](#26-definition-of-done)
27. [First implementation brief](#27-first-implementation-brief)
28. [Research references](#28-research-references)

---

## 1. Executive decision

Build GPT++ as a **small, statically typed, managed, general-purpose language**, with a deterministic compiler, a native-code backend, and a first-class protocol for AI-generated edits.

The project consists of three separately testable layers:

| Layer | Responsibility | What must remain independent |
|---|---|---|
| Language | Meaning of programs, types, effects, errors, modules, and contracts | Must be usable without an LLM |
| Compiler and runtime | Check programs, generate executables, implement specified behavior | Must not call an LLM to decide meaning or correctness |
| AI authoring tools | Supply relevant context, accept bounded edits, expose diagnostics, optionally constrain generation | Must not bypass compiler checks or silently grant authority |

The proposed implementation is a Rust compiler frontend, a GPT++-owned typed intermediate representation, an executable reference interpreter, and an LLVM native backend. Reusing LLVM does not make GPT++ a transpiler: GPT++ owns its grammar, type rules, semantics, diagnostics, runtime interface, and lowering. LLVM supplies machine-code infrastructure, as illustrated by its language-frontend documentation. [R1]

**Make an expression addressable by behavior as well as by source.** A caller's wrong result is often the only clue an agent gets. In the scalar profile, the compiler can follow that call, identify the expressions it visited and report their types, visible bindings and observed results. An agent can submit a checked edit at the same revision and byte range. The authoring tool can search a bounded expression grammar and offer only changes that satisfy supplied examples. If several changes fit, it can identify a call for which an additional expected result would disambiguate them. These operations also work offline.

Evaluate each operation by what an agent can correctly accomplish with it. For repair, measure accepted changes, unanswered cases, tool time, model usage and any additional expected results supplied. Report each measure alongside the comparator, the task and the evidence that supports it. [Trace reference](scalar-language.md#trace-a-call) · [Authoring interface](../tools/README.md#search-for-an-edit-with-public-examples) · [Development evidence](../bench/expression/results/repair.md)

### Scalar operations prompted by models’ failed edits

Qwen2.5-Coder 7B proposed a correct rounding expression that converted a remainder test to an integer. It also proposed integer minimum and maximum for a bounded accumulator. The earlier compiler rejected both forms. Explicit conversion with `as I64` now yields 0 for false and 1 for true. The integer functions `min`, `max` and `clamp` evaluate their arguments under the same checked arithmetic rules as other calls.

Adding these forms let the same Qwen replies solve all three locally authored contracts. One first reply and two saved retries passed every withheld test. The six historical GPT++ trials and StarCoder2’s three locally authored trials still had zero accepted changes. The operators were chosen after the failures were inspected. A fresh matched study can test how often a model independently chooses useful expressions on other tasks. [Original trials](../bench/expression/results/fresh-agent.md) · [Replay including extra direct checks](../bench/expression/results/compat.md)

### What the execution-guided study established

On Redis, the search generated a change that passed independent caller tests. A deterministic first choice and both models selected it. On FastLED, six alternatives matched the original examples. Two additional expected values from a reference calculation uniquely identified the passing edit. On Go, the bounded search produced no candidate for the Gregorian year boundary. This separates two practical authoring problems. More information can resolve a choice between available edits. Generating a missing edit requires a different search space or a model-authored proposal. [Autonomous repair trials](../bench/expression/results/repair.md) · [Oracle-assisted follow-up](../bench/expression/results/distinguish.md)

### Earlier maintenance priorities

| Priority | Evidence | Engineering decision |
|---|---|---|
| 1. Express the behavior that changes | In 25 of 38 failed GPT++ and typed-Python edits reviewed across v5–v6, the model missed a decision branch, its priority or the default behavior. | Prefer a bounded native body edit in the Qwen workflow. Preserve ordered exceptions as an optional checked artifact. Both models failed all eight rule edits despite eight working handwritten solutions. |
| 2. Reduce what the model must read | Input accounted for 42,676 of the 47,710 tokens spent across those arms. | Start with the target, its current behavior, the requested change and public examples. Charge syntax guides, previous completions and any caller excerpts to the trial that uses them. |
| 3. Make failure feedback actionable | The 40 retries in the reviewed arms added two accepted edits. Another 11 terminal failures involved incorrect arithmetic or cyclic mapping. | Expose one-shot authoring and a retry triggered by an actual caller failure. The compiler can invert an unchanged caller’s checked arithmetic to give the model a necessary target result. Count the cost and acceptance yield of each retry. |
| 4. Attribute gains to the right layer | Existing task sets favor small, single-module scalar edits. | Give Python and Rust the same protected edit scope, information and validation. Track native GPT++ body edits separately from the optional rule frontend. Replicate promising results on identified upstream changes and a second model before widening the claim. |

**Decision after the upstream transfer.** Keep the compact native maintenance preset. Treat ordered rules as an opt-in surface for explicit exceptions. Qwen used 500.20 tokens per accepted native GPT++ edit on the development tasks. On three upstream changes, the selected GPT++ workflow passed one while selected Python and Rust passed zero. The best observed GPT++ and Python alternatives each passed one, at 1,120 and 1,121 tokens. StarCoder2 passed none of the transfer cases. The next language experiment should protect unchanged expressions *inside* a target. For example, a changed border comparison should not require writing a whole geometry predicate. Compare the same expression-level operation in Python and Rust on new upstream changes. [Development and transfer results](../bench/policy/README.md)

The language retains a human-reviewable native representation. A checked editing surface can succeed on a workload even if native syntax is relatively expensive for an existing model. Keep the measured choice reversible while the general-purpose language grows. [Failure review](../bench/policy/diagnosis.md) · [Experiment protocol](../bench/policy/protocol.md) · [Ordered-rule authoring](../tools/policy.md)

---

## 2. What AI efficiency actually means

### 2.1 Optimize the complete workflow

For a fixed benchmark task set, define:

```text
accepted_i = 1 when task i meets the independent acceptance specification;
             0 otherwise.

cost_i = sum(billed model usage across all calls for task i)
       + sum(tool, compiler, test and runner costs for task i)

cost_per_accepted_task = sum(cost_i) / sum(accepted_i)
```

Charge each resource once. Attribute a call to initial generation or repair for analysis. Its bill already includes any billed context or diagnostic tokens. Count abandoned tasks, invalid patches, compiler failures and timeouts. If nothing passes, report zero acceptances and no finite cost per accepted task. Publish acceptance alongside cost so that completing a few cheap tasks cannot conceal a high overall failure rate.

Express components in a common unit when adding them. A monetary estimate requires documented prices; a hardware-cost estimate requires documented hardware and utilization. Do not add tokens, milliseconds, and dollars as if they were interchangeable. Also publish the raw measurements so the result does not depend on one pricing scheme.

For maintenance workloads, measure a second quantity:

```text
change_cost = total cost of delivering an accepted change
              while preserving the specified existing behavior
```

A language that produces a short first draft but repeatedly breaks neighboring modules may be worse than a longer language with reliable localized edits.

### 2.2 Measure several distinct resources

| Resource | Required observations |
|---|---|
| Model input | Specification, language guide, examples, retrieved APIs, prior messages, diagnostics |
| Model output | Code, patch envelopes, explanations required by the protocol, billed reasoning tokens when exposed |
| Context reuse | Cached versus uncached input, cache preparation, cold and warm sessions |
| Interaction | Calls, retries, tool round trips, repair iterations, rejected edits |
| Tool compute | Parsing, checking, linking, tests, solver use, grammar construction and masking |
| Execution | Time, peak memory, allocation behavior, startup, artifact size |
| Human involvement | Review effort and interventions; report separately unless a valuation is explicit |

Model-token savings are tokenizer-specific. Tokenization includes normalization, pre-tokenization, and learned token models, so fewer visible characters do not establish fewer model tokens. Measure with the actual tokenizers or provider-reported usage. [R3]

### 2.3 Important limits on the optimization thesis

**A smaller grammar does not automatically make each neural-network inference step cheaper.** It may improve validity or reduce output length, but it can also add decoding work. The experiment must measure actual end-to-end cost and latency.

**A shorter program is not automatically easier to generate.** Removing names, types, or intermediate values can remove information useful for reasoning. Compression after generation saves storage or transport, not necessarily model generation cost.

**A new language starts with a familiarity disadvantage.** Existing code models have uneven exposure to programming languages. Research on resource distribution and low-resource transfer makes this a material concern, not a minor onboarding detail. [R7][R8]

**Type-correct is not specification-correct.** A perfectly typed function can implement the wrong business rule. Contracts can also encode the wrong rule. Independent tests and review remain necessary.

### 2.4 Compare correctness, resources and maintainability

Evaluate acceptance, model and tool costs, latency, runtime behavior and maintainability on the same workload. A change that saves tokens while increasing retries or reducing acceptance should report all three effects. Report the applicable safety and resource constraints.

Fine-tuning and ecosystem-building have fixed costs. Report both marginal inference cost and an amortized estimate:

```text
amortized_cost_per_task = marginal_workflow_cost
                        + adaptation_cost / expected_task_volume
                        + allocated_tooling_cost / expected_task_volume
```

State the assumed volume. Do not claim a deployment is cheaper by excluding the cost of teaching the model the new language.

---

## 3. Evidence, hypotheses, and corrections

### 3.1 What existing work supports

| Evidence | Relevance to GPT++ | What it does not establish |
|---|---|---|
| SynCode studies grammar-constrained generation. [R4] | Export a grammar and evaluate constrained decoding | Syntactic validity does not prove task correctness |
| Type-constrained generation studies constraints beyond grammar. [R5] | Expose expected types and compiler checks to authoring tools | A full incremental type-aware decoder is not automatically cheap or complete |
| Research on constrainer/model/language misalignment reports that unsuitable constraints can harm generation. [R6] | Test constrained and unconstrained paths; keep a fallback | More constraints are not universally better |
| MultiPL-T studies validated transfer into lower-resource languages. [R7] | Build executable examples and validated translation pairs | Synthetic translations are not guaranteed correct merely because they compile |
| A programming-language resource taxonomy documents major corpus imbalance. [R8] | Evaluate cold-start performance and adaptation separately | Corpus size alone does not determine capability |
| Koka demonstrates a language with effect types. [R9] | Effects are a practical precedent, not an invented GPT++ feature | GPT++ will not inherit Koka's soundness or performance by copying notation |
| Dafny provides a reference for contracts and program verification. [R10] | Separate checks, tests, and proved obligations | Arbitrary software cannot be automatically certified against unstated intent |
| EvalPlus strengthens code evaluation with more extensive tests. [R11] | Use demanding independent oracles | Passing tests is not a universal proof |
| LiveCodeBench includes evolving tasks and multiple coding capabilities. [R12] | Include repair and freshness controls | A live benchmark is not automatically free of contamination for every model |
| ShortCoder studies token-efficient code generation within Python. [R17] | Compare GPT++ against improved existing-language generation | A new language is not required for every efficiency gain |

These references motivate experiments. None measures GPT++ itself.

#### Premise review, 19 November 2026

The investment decision depends on the cost of an **accepted change**. SynCode studied syntactic validity, EvalPlus found that stronger tests can change model rankings, and ShortCoder measured generation savings within Python. Together they justify measuring repairs and testing a strong existing-language control. None estimates the cost of teaching a model GPT++ or maintaining a GPT++ repository. [SynCode](https://arxiv.org/abs/2403.01632) · [EvalPlus](https://arxiv.org/abs/2305.01210) · [ShortCoder](https://arxiv.org/abs/2601.09703)

Two different decisions follow. The scalar compiler earns further engineering work by correctly executing specified programs across independent engines. Language expansion earns research investment through a paired authoring pilot against existing languages. Keep the gates independent so that a working compiler cannot count as evidence of cheaper authoring.

### 3.2 Hypotheses to test

| ID | Hypothesis | Falsification signal |
|---|---|---|
| H1 | Explicit interfaces reduce repository-context requirements | The same acceptance needs equally large context |
| H2 | A small, familiar syntax lowers generation and repair cost | Training unfamiliarity overwhelms any syntax benefit |
| H3 | Mandatory error types reduce incorrect error-path handling | Errors shift into verbose but still incorrect handling |
| H4 | Effect summaries help avoid unintended external behavior | Summaries add tokens without reducing relevant mistakes |
| H5 | Symbol-level patches outperform repeated file replacement | Patch overhead and conflicts exceed saved generation |
| H6 | Structured diagnostics reduce repair iterations | Explanations are large, misleading, or produce repair loops |
| H7 | Validated adaptation data improves GPT++ use economically | Gains fail to cover training and maintenance costs |
| H8 | Compiler-generated boilerplate is cheaper than model-generated boilerplate | Derivations require too much hidden configuration or obscure behavior |

### 3.3 Corrections to attractive but unsafe shortcuts

Do not replace descriptive names with numbers by default. Internal compiler temporaries may use numeric identifiers; model-facing APIs should retain semantic names unless controlled measurements favor another representation.

Do not interpret “one canonical syntax” as “one possible program for each behavior.” GPT++ can standardize formatting and syntax without trying to solve general program equivalence.

Do not treat a precondition as a filter. A declaration such as `requires age >= 18` constrains allowed inputs; it does not select adults out of a list. Filtering belongs in executable code, while a contract describes an obligation or result property.

Do not let the compiler invent missing business logic. An incomplete body must remain incomplete. The authoring layer may propose a repair, but compilation must not quietly ask a model to fill gaps.

Do not design the public language as raw LLVM IR. Low-level layout, control flow, and memory operations belong in compiler output, not in the model's routine authoring burden.

---

## 4. Product boundaries and initial users

### 4.1 Meaning of general-purpose

GPT++ must support arbitrary user-defined algorithms, functions, recursion, iteration, data structures, modules, persistent data, and explicit interaction with the operating environment. It is not a prompt notation, workflow-only DSL, or a finite catalog of AI tools.

The first production profile targets command-line applications, data transformations, business logic, synchronous services, automation, and reusable native libraries. Useful support for these domains is more important than immediately matching every ecosystem.

### 4.2 Initial platform policy

Use native Apple Silicon macOS and x86-64 Linux as the first development/test targets. Add native Windows x86-64 before declaring the planned cross-platform 1.0 profile complete. Architecture and OS support must be claimed individually after runtime, ABI, linker, and integration tests—not inferred from LLVM target availability.

An experimental WebAssembly/WASI target can follow the native vertical slice. It is valuable for controlled execution, but a runtime and host-interface port are still required. A backend's ability to emit WebAssembly does not automatically provide the GPT++ standard library.

### 4.3 Explicit non-goals for 1.0

GPT++ 1.0 is not an operating-system kernel language, hard-real-time language, GPU kernel language, drop-in Python interpreter, C++ replacement, or universal browser UI framework. It does not require self-hosting, a custom tokenizer, a proprietary model, unrestricted metaprogramming, or AI calls during compilation.

Built-in parallel shared-memory concurrency and general user-defined effect handlers are deferred. A sequential general-purpose language is a legitimate initial product; concurrency must not be bolted on with undefined sharing and cancellation rules.

### 4.4 Three demonstration applications

The release demonstrations should be a file-based JSON transformation tool, a small capability-restricted HTTP service, and a multi-module application maintained through several independently evaluated changes. Each must be buildable offline after dependency fetching and executable without an LLM service.

---

## 5. Architecture decisions

These are defaults for the first implementation, not claims that alternatives are inferior in all settings.

| Decision | Selected default | Reason and trade-off |
|---|---|---|
| Implementation language | Rust | One implementation stack for frontend, tools, and most runtime code; requires explicit control around backend/FFI boundaries |
| Execution | Ahead-of-time native compilation plus reference interpreter | Real deployable programs and a semantic comparison path |
| Backend | LLVM | Reuse machine-code infrastructure; accept dependency size and integration work |
| Source | UTF-8 text with familiar keywords and fixed syntax | Low onboarding cost and reviewability |
| Extension/tool | `.gpp`, `gpp` | Working identifiers, subject to public-name checks |
| Typing | Static nominal records/enums; explicit function boundaries; local inference | Useful compiler feedback without annotating every local value |
| Effects | Explicit finite effect sets on function signatures | Visible external behavior; some verbosity |
| Errors | `Result<T, E>` and exhaustive matching | No hidden exception propagation |
| Missing values | `Option<T>` | No implicit null |
| Memory | Managed non-moving tracing heap; value-oriented source semantics | Simpler authoring than lifetime management; runtime and GC engineering cost |
| Mutation | Local mutable bindings; immutable aggregate values initially | Easier reasoning; update-heavy workloads need efficient library representations |
| Generics | First-order parametric generics, monomorphized | Predictable specialization; code-size limits required |
| Modules | Explicit imports, public/private declarations, generated interfaces | Local context and reliable dependency checking |
| AI editing | Transactional symbol-level changes | Less regeneration; requires a versioned protocol |
| Verification | Checks and tests first; bounded optional solver support later | Avoid making every program a proof project |
| FFI | Audited C-ABI boundary through declared native packages | Ecosystem access with an explicit trust boundary |
| Packages | Locked, content-verified dependencies; no build scripts by default | Reproducibility and reduced supply-chain authority |
| Model dependence | None in language semantics | Any model or human can author code |

A full garbage collector, effect checker, package system, and agent protocol are substantial work. The roadmap deliberately implements a scalar native compiler before all of them.

---

## 6. Representations and canonical source

### 6.1 Four representations, one semantic checking path

```text
Human or AI author
    |
    +--> GPT++ source text ------------------+
    |                                       |
    +--> structured source-AST edit ---------+--> parse/validate
                                                |
                                                v
                                      name/type/effect checking
                                                |
                                                v
                                       GPT++ typed internal IR
                                                |
                                                v
                                            LLVM IR
                                                |
                                                v
                                      object file + runtime + linker
                                                |
                                                v
                                          native executable
```

Source text is the normal version-controlled artifact. A structured edit operates on source-level constructs, not on trusted typed compiler state. Every entry path must pass the same checking pipeline.

The public AST schema must reject unknown tags, missing mandatory fields, invalid identifiers, duplicate fields, and impossible structures. It must not accept an agent's assertion that a node is “already checked.”

### 6.2 Canonical formatting

One formatter controls indentation, delimiter placement, whitespace, and documented layout. Semicolons terminate simple statements; braces delimit blocks; indentation is not semantic. Comments and documentation are preserved.

Formatting must not reorder effectful expressions, record initializer evaluation, imports whose order becomes meaningful, or declarations that affect tooling identity. It is a syntax-preserving operation, not a speculative optimizer.

Canonical source does not require removing every optional type annotation. Where annotations are allowed, the formatter preserves them rather than changing inference behavior.

### 6.3 What the model should generate

Prefer complete small functions, explicit API changes, or bounded replacements of a function body. Let the compiler generate derived JSON codecs, ABI wrappers, import indexes, specialization bodies, and temporary names.

Compare three authoring formats empirically: canonical source, schema-constrained source AST, and compact patch envelopes carrying source fragments. JSON is useful for validation but can be more verbose than code; it is not the default winner merely because it is structured.

### 6.4 What not to expose as a stable authoring contract

Typed compiler IR, SSA numbering, native layouts, and optimizer-specific instructions remain internal. Publishing these as the primary language would couple every AI and tool to compiler implementation changes and force low-level decisions into generation.

---

## 7. Language specification: proposed baseline

The rules in this section are the proposed semantic baseline. The bootstrap implements the scalar subset in Section 27. Later phases add the remaining features.

### 7.1 Lexical and naming rules

Source files use UTF-8. Keywords and identifiers initially use ASCII; strings and comments support Unicode. Identifier spelling is case-sensitive. Disallow bidirectional control characters outside escaped string data, and warn about suspicious controls in comments. Unicode identifiers can be a later edition feature after normalization and confusable policies are specified.

Use `snake_case` for functions/variables/modules and `PascalCase` for named types. These are formatter/lint conventions, not type semantics. Reserved keywords cannot be identifiers. The first edition has no custom operators, implicit semicolons, preprocessor, or user-defined macro expansion.

A module declares its name. Imports name a module and introduce a single explicit namespace. Public symbols use `pub`; other declarations are module-private. No wildcard imports or implicit imports except a small specified prelude containing fundamental types and constructors.

### 7.2 Types

| Category | Initial design |
|---|---|
| Scalar | `Bool`, `I32`, `I64`, `U8`, `U32`, `U64`, `F64`, `Unit` |
| Text/data | `String` as valid UTF-8; `Bytes` as uninterpreted bytes |
| Collections | `List<T>`, insertion-ordered `Map<K, V>`, `Set<T>` with specified iteration order |
| Products | Named records, tuples |
| Alternatives | Named enums with optional payloads |
| Absence/failure | `Option<T>`, `Result<T, E>` |
| Callable | Function/closure types with parameter, return, and effect information |
| Opaque host values | Capability and resource types constructed only by trusted interfaces |

Add other widths and numeric facilities only with specified conversion and overflow behavior. Do not quietly make `Int` vary by platform; the baseline uses fixed-width names.

Record and enum types are nominal: two declarations with identical fields are not automatically interchangeable. Generic containers are invariant. There is no implicit top type, implicit downcast, or dynamic dispatch through untyped values.

Function parameters, return types, and effect sets are explicit. Local inference is permitted when the type is unique. Empty collections and ambiguous generic calls need an annotation or explicit type arguments. Recursive functions require explicit signatures and are checked as a declared strongly connected group.

First-order generics are sufficient initially. There are no higher-kinded types, dependent types, implicit dictionaries, user-defined overload resolution, or inheritance hierarchy. Generic algorithms can accept explicit comparator/serializer functions. Built-in equality/key eligibility rules must be documented rather than hiding a general trait solver in the compiler.

### 7.3 Values and mutation

`let` binds an immutable value. `var` creates a local reassignable binding. Assigning a list or record gives value semantics; subsequent rebinding does not mutate an alias. The implementation may share immutable storage without exposing pointer identity.

Closures capture values. They do not silently capture a mutable reference to a local `var`; a captured value is the value at closure creation. Shared mutable cells are not part of the initial language. Graphs can be represented explicitly using node identifiers and maps.

Local loops and rebinding do not by themselves add an external effect. There are no mutable global variables in the baseline. Module initialization consists only of checked constants and declaration registration, not arbitrary hidden I/O.

### 7.4 Functions and control flow

The baseline includes function definitions, calls, explicit `return`, `if`/`else`, `while`, `for ... in`, `break`, `continue`, and exhaustive `match`. Both ordinary loops and recursion are intentional: reducing syntax must not force awkward encodings of normal algorithms.

Boolean conditions require `Bool`; there is no truthiness. Operands and call arguments evaluate left to right. `&&` and `||` short-circuit. A record literal evaluates initializer expressions in written order; the formatter cannot reorder them.

A `for` loop visits a collection snapshot in its specified order. Rebinding the source variable inside the loop does not alter that snapshot. A `match` on an enum must cover all variants; unreachable duplicate arms are rejected. Expression-valued branches must have one compatible result type. Non-`Unit` functions must return on every normally completing path.

### 7.5 Operators and numeric behavior

Arithmetic operators are fixed built-ins. There is no user-defined operator overloading. Integer conversions are explicit; integer literals can acquire an expected integer type when in range, otherwise default to `I64` when unambiguous.

Integer `+`, `-`, and `*` use checked arithmetic in every build mode. Overflow produces a defined runtime fault. Explicit standard-library operations provide wrapping, saturating, and result-returning checked alternatives. Division by zero and signed minimum divided by `-1` are defined faults, not undefined behavior. Signed division truncates toward zero. The remainder has the dividend’s sign when nonzero. Remainder by zero faults. The remainder of signed minimum by `-1` is zero. Checked unary negation of signed minimum faults.

Shifts use explicit library functions initially, with defined range checks. There are no C-style implicit promotions.

`F64` follows the language's documented binary floating-point profile: preserve ordinary signed-zero and NaN behavior, disable implicit fast-math transformations, and do not promise cross-platform identical transcendental results. Floating-point map keys require an explicit key wrapper with defined NaN/zero treatment; raw `F64` is not an initial map-key type.

Defined arithmetic faults are observables. An optimization cannot eliminate an overflow fault merely because the arithmetic result is unused. Resource exhaustion is handled separately from ordinary arithmetic semantics.

### 7.6 Text and collections

`String` always contains valid UTF-8. Conversion from `Bytes` returns a `Result`. APIs distinguish byte length, Unicode scalar iteration, and grapheme-oriented operations. An unspecified “character index” is not permitted.

The initial language has collection literals but no unchecked indexing syntax. `list.get(values, index)` returns `Option<T>`; explicit checked access can return a typed error. Slices validate bounds. This avoids a hidden unchecked access path.

Map iteration is insertion-ordered. Replacing an existing value preserves position; removing and reinserting a key places it at the end. Hash randomization may protect implementation internals but must not change this visible order. Map-key support begins with specified scalar/text/byte types; richer keys require explicit encodings or later documented structural rules.

### 7.7 Errors and faults

Expected operational failures are values: parsing can fail, a file can be missing, a network peer can disconnect. These return `Result<T, E>`.

The postfix `?` operator is the single propagation shorthand. It extracts an `Ok` value or returns the exact `Err` from the current function. The function must return a `Result` with the same error type. Error-type conversion is explicit; there are no invisible conversion hooks.

Unused `Result` expressions and unused result bindings are hard diagnostics by default. This discourages accidental loss of errors but does not prove that every error is handled appropriately.

Programming faults—such as violated runtime contracts or checked integer overflow—terminate the current program execution through a documented fault mechanism. In the initial sequential runtime, faults are not catchable exceptions. Recoverable behavior requires an explicit result-returning operation instead. Allocation failure terminates with a defined resource-exhaustion category where the runtime can report it safely.

There is no general exception unwinding, implicit null dereference, or model-generated exception recovery.

### 7.8 Effects

Every function signature has an explicit effect set:

```gpp
fn normalize(value: String) -> String !{} { ... }
fn read_config(root: cap.FsRead, path: fs.RelPath)
    -> Result<String, fs.Error> !{fs_read} { ... }
```

Examples of initial external effect labels are `console`, `fs_read`, `fs_write`, `net`, `clock`, `random`, `process`, and `ffi`. Labels specify categories of behavior, not exact permission grants.

For an ordinary call, the callee's effects must be a subset of the caller's declared effects. Function values retain their effect information. A pure callback parameter cannot receive an effectful callback. Initial higher-order collection functions accept pure callbacks; effectful iteration uses ordinary loops. General effect-polymorphic library APIs are deferred until their rules and diagnostics are implemented and tested.

`!{}` means no modeled externally observable effect. It does **not** promise termination, absence of allocation, absence of runtime faults, constant memory use, or identical floating-point results across all machines. Runtime allocation and compiler-internal optimization effects must not be confused with this source-level set.

### 7.9 Capabilities

An effect declaration is not permission. An operation also requires an opaque capability value, such as `cap.FsRead`, provided by the launcher or a trusted caller.

A filesystem capability carries an approved root and operation restrictions. Paths are validated relative paths, and enforcement must handle symlinks and race conditions through safe host primitives rather than string-prefix checks. Network capabilities restrict allowed destinations through a defined host policy. Code cannot manufacture capabilities from strings or integers.

The executable's requested capabilities and the host's grants must both allow the operation. Denied startup grants produce a startup error; the launcher does not fill a required capability field with null or silently widen permissions.

### 7.10 Contracts

A top-level `contract` binds integer inputs over inclusive finite intervals and Boolean inputs over both truth values. Its body is a Boolean expression that can call checked module functions. The offline verifier enumerates the declared inputs. When evaluating a contract for an edit, the user-supplied source predicate stays fixed. A passing result covers the declared finite domain and the predicate that was written. A repair menu retains multiple edits when all satisfy the stated rules. In a development study, two signed-carry edits behaved identically on the declared domain and differed on inputs outside it. [Domain-scope measurement](../bench/contracts/results.md) [Current contract syntax and verification](scalar-language.md#verify-a-finite-contract)

A separate proposed feature would attach preconditions and postconditions to function signatures:

```gpp
fn clamp(value: I64, lower: I64, upper: I64) -> I64 !{}
requires lower <= upper
ensures result >= lower && result <= upper
{
    if value < lower { return lower; }
    if value > upper { return upper; }
    return value;
}
```

`requires` defines a caller obligation. `ensures` defines a property of normal return. The identifier `result` is available only in a postcondition. Runtime checks remain enabled unless a supported verification process justifies their removal under the exact build assumptions.

The proposed precondition and postcondition sublanguage would be restricted to side-effect-free, terminating scalar expressions and explicitly approved total intrinsics. General recursive calls, unbounded quantifiers, I/O, and arbitrary loops are excluded. Verification uses the same bounded integer semantics as execution, including overflow obligations.

### 7.11 Source holes during editing

The agent/editor representation can include an explicit `Hole` node with an expected type, effect allowance, and local scope. A hole is an editing artifact, not executable source semantics. Normal `check`, `build`, packaging, and release commands reject any unresolved hole. No release artifact may contain an automatic fallback body.

---

## 8. Examples of GPT++

These are proposed source examples. They have not been compiled by a GPT++ implementation.

### 8.1 Pure data processing

```gpp
module example.users;
use std.list;

pub record User {
    name: String,
    age: I64,
}

pub fn adult_names(users: List<User>) -> List<String> !{} {
    var names: List<String> = [];
    for user in users {
        if user.age >= 18 {
            names = list.push(names, user.name);
        }
    }
    return names;
}

test "adult_names keeps input order and includes age 18" {
    let users = [
        User { name: "Alex", age: 17 },
        User { name: "Sam", age: 18 },
        User { name: "Zoë", age: 24 },
    ];
    assert adult_names(users) == ["Sam", "Zoë"];
}
```

This intentionally uses familiar, explicit operations. It does not claim to be shorter than a Python comprehension. Its proposed benefit is a stable signature, bounded dependencies, simple semantics, and compiler-checkable behavior. A pipeline form should be added only if its measured benefit justifies another construct.

The collection implementation should use an efficient persistent representation or a proven uniqueness optimization; `list.push` must not accidentally force a full copy at every iteration. Performance tests must detect quadratic growth.

### 8.2 Explicit recoverable failure

```gpp
module example.math;
use std.int;

pub enum DivideError {
    ZeroDivisor,
    Overflow,
}

pub fn divide(numerator: I64, denominator: I64)
    -> Result<I64, DivideError> !{} {
    if denominator == 0 {
        return Result.Err(DivideError.ZeroDivisor);
    }
    if numerator == int.min_i64() && denominator == -1 {
        return Result.Err(DivideError.Overflow);
    }
    return Result.Ok(numerator / denominator);
}
```

The ordinary division operator may fault; this function explicitly translates both specified failure conditions into recoverable errors. This is behavior, not a compiler inference about what the programmer probably intended.

### 8.3 A capability-based entry point

```gpp
module hello.main;
use std.cap;
use std.io;

pub fn main(app: cap.App) -> Result<Unit, io.Error> !{console} {
    io.write_line(app.console, "Hello, GPT++")?;
    return Result.Ok(());
}
```

`cap.App` is an entry-point context generated from the package's declared capability interface. Only the launcher constructs it. Ordinary helper functions receive the smallest required capability rather than the entire application context.

The launcher translates `Ok(())` to success, an uncaught `Err` to the documented application-error exit status, and faults to the documented fault status. Exact exit codes are fixed in the runtime specification before the first public release.

### 8.4 Typed decoding with explicit error mapping

```gpp
module example.config;
use std.cap;
use std.fs;
use std.json;

@derive(json.Codec)
pub record Config {
    host: String,
    port: U32,
}

pub enum ConfigError {
    Read(fs.Error),
    Decode(json.Error),
    InvalidPort,
}

pub fn load(root: cap.FsRead, path: fs.RelPath)
    -> Result<Config, ConfigError> !{fs_read} {
    let text = match fs.read_text(root, path) {
        Result.Ok(value) => value,
        Result.Err(error) => { return Result.Err(ConfigError.Read(error)); },
    };

    let config = match json.decode::<Config>(text) {
        Result.Ok(value) => value,
        Result.Err(error) => { return Result.Err(ConfigError.Decode(error)); },
    };

    if config.port == 0 || config.port > 65535 {
        return Result.Err(ConfigError.InvalidPort);
    }
    return Result.Ok(config);
}
```

`@derive(json.Codec)` is a compiler-controlled derivation, not arbitrary code execution at compile time. It generates ordinary checked codec code. A schema-valid integer is still not necessarily a valid network port; the additional business rule remains explicit.

### 8.5 Minimal package layout and manifest

```text
hello/
  gpt.toml
  gpt.lock
  src/
    main.gpp
  tests/
    hello_test.gpp
```

```toml
[package]
name = "hello"
version = "0.1.0"
edition = "1"

[toolchain]
compiler = "0.3.0"
stdlib = "0.3.0"

[entry]
module = "hello.main"
function = "main"

[capabilities]
console = true
fs_read = []
fs_write = []
net = []
process = false
ffi = false

[dependencies]
```

The versions above illustrate the proposed manifest format; they are not published releases. The final lockfile also records artifact digests, transitive dependencies, target/runtime compatibility, and the actual pinned toolchain build. The manifest requests capabilities; launch policy decides whether to grant them.

The package-oriented commands below are planned. The scalar CLI takes a single source path. [Current commands](scalar-language.md#inspect-and-diagnose)

```sh
gpp fmt --check
gpp check --format=json
gpp test --sandbox
gpp build --target aarch64-apple-darwin
gpp api --module hello.main --format=json
```

---

## 9. Grammar and parsing strategy

### 9.1 Parser implementation

Use a hand-written lexer, recursive-descent declaration/statement parser, and Pratt expression parser. Keep a lossless concrete syntax tree for comments, formatting, and editor recovery, then lower into a smaller source AST.

The authoritative grammar belongs in `spec/grammar.ebnf`, with a generated or checked equivalent for constrained generation. A grammar exporter must not silently implement a narrower language than the compiler accepts. Test both directions on generated valid programs and adversarial invalid strings.

The first grammar supports a conservative subset; unsupported future features produce a version-specific diagnostic rather than partial interpretation. Parser recovery is for editing only: a recovered tree with syntax errors cannot be compiled into an executable.

### 9.2 Grammar outline

This outline fixes the main shape. It is not a replacement for the complete lexical, precedence, attribute, generic, pattern, and type grammars required before implementation release.

```ebnf
module          = "module", path, ";", { import_decl }, { declaration } ;
import_decl     = "use", path, ";" ;
declaration     = { attribute }, [ "pub" ],
                  ( function_decl | record_decl | enum_decl | constant_decl )
                | test_decl ;

function_decl   = "fn", identifier, [ generic_params ],
                  "(", [ parameters ], ")", "->", type, effects,
                  { contract }, block ;
parameters      = parameter, { ",", parameter }, [ "," ] ;
parameter       = identifier, ":", type ;
effects         = "!", "{", [ identifier, { ",", identifier } ], "}" ;
contract        = ( "requires" | "ensures" ), expression ;

record_decl     = "record", identifier, [ generic_params ],
                  "{", { identifier, ":", type, "," }, "}" ;
enum_decl       = "enum", identifier, [ generic_params ],
                  "{", { enum_variant, "," }, "}" ;
enum_variant    = identifier, [ "(", type, { ",", type }, ")" ] ;
constant_decl   = "const", identifier, ":", type, "=", expression, ";" ;
test_decl       = "test", string_literal, block ;

block           = "{", { statement }, "}" ;
statement       = binding | assignment | return_stmt | if_stmt | while_stmt
                | for_stmt | match_stmt | assert_stmt | expression_stmt
                | "break", ";" | "continue", ";" ;
binding         = ( "let" | "var" ), identifier, [ ":", type ],
                  "=", expression, ";" ;
assignment      = identifier, "=", expression, ";" ;
return_stmt     = "return", expression, ";" ;
if_stmt         = "if", expression, block, [ "else", ( block | if_stmt ) ] ;
while_stmt      = "while", expression, block ;
for_stmt        = "for", identifier, "in", expression, block ;
assert_stmt     = "assert", expression, ";" ;
expression_stmt = expression, ";" ;

match_expr      = "match", expression, "{", { match_arm }, "}" ;
match_stmt      = match_expr, ";" ;
match_arm       = pattern, "=>", ( expression | block ), "," ;
call_suffix     = [ "::", "<", type, { ",", type }, ">" ],
                  "(", [ arguments ], ")" ;
path            = identifier, { ".", identifier } ;
```

Expression forms also include literals, list/tuple/record construction, qualified names, field access, calls, function literals, unary operators, fixed binary operators, postfix `?`, and matching. `()` is the `Unit` value. A block normally has type `Unit`; a block that returns from the enclosing function is non-returning and can inhabit an arm of any expected result type.

Use `::<Type>` for explicit generic call arguments so type arguments are unambiguous against comparison operators. Generic declarations and types use ordinary angle brackets. Arbitrary user operators and shift-operator token ambiguity are absent from the initial grammar.

### 9.3 Small formal core

Define the typing judgment as:

```text
Γ ⊢ expression : Type ! Effects
```

Here, `Γ` contains local bindings and resolved imported signatures. At minimum, write and test rules for literals, variable lookup, binding, assignment, calls, function values, branch joins, `Result` propagation, enum matching, generic instantiation, and effect inclusion.

Specify progress and preservation goals for a reduced core, explicitly accounting for defined faults and possible nontermination. A mechanized proof of that core is a later assurance activity; it must not be represented as a proof of the full compiler, runtime, FFI, and optimizer.

### 9.4 Compatibility tests

Maintain a single example corpus used by the parser, formatter, interpreter, compiler, grammar-constrained decoder, and documentation tests. Required properties include parse/format/parse semantic equivalence, stable formatting, meaningful recovery on truncated input, and rejection of every documented negative example.

---

## 10. Compiler architecture

### 10.1 Pipeline and responsibilities

| Stage | Output | Required invariant |
|---|---|---|
| Package resolution | Locked module graph | All dependencies are available, content-verified, and edition-compatible |
| Lexing/parsing | Lossless syntax tree and AST | No unresolved syntax errors on build paths |
| Name resolution | Bound AST | Every symbol and field refers to a unique declaration |
| Type checking | Typed high-level IR | All terms, calls, branches, and patterns satisfy the type rules |
| Effect/capability checks | Checked high-level IR | Calls respect effect bounds; host APIs receive required capability types |
| Contract elaboration | Checks and proof obligations | Checks have defined placement and are not silently omitted |
| Core lowering | Small typed core IR | Explicit evaluation order, error paths, and logical faults |
| Specialization | Monomorphic core instances | No unchecked generic instantiation or unbounded expansion |
| CFG/SSA lowering | Mid-level IR with basic blocks | Valid control-flow graph and typed value definitions |
| Runtime lowering | Explicit allocation, roots, host calls | Managed objects remain rooted and ABI rules are satisfied |
| Native lowering | LLVM IR | Source semantics are preserved; unsafe assumptions are not invented |
| Object/link | Native executable or library | Correct runtime, sysroot, target ABI, and dependency artifacts |

A compiler frontend can use LLVM to generate object code without delegating the language definition to another source language. This is the architectural precedent, not a claim that the LLVM tutorial is a production compiler blueprint. [R1]

### 10.2 Ownership of intermediate representations

Maintain three GPT++ representations:

**HIR: high-level intermediate representation.** Resolved names, original structure, types, effect sets, source locations, and contracts. Suitable for diagnostics and interface extraction.

**Core IR.** A small expression language in which complex expressions are decomposed into explicit evaluation steps. It defines a manageable semantic core for the interpreter, desugaring tests, and verification translations.

**MIR: mid-level intermediate representation.** Control-flow blocks, explicit branches, typed values, runtime operations, and fault paths. Use SSA values and block parameters, with verifiers after every transformation.

These are internal representations with their own versioning. Public source-AST tools must not become dependent on MIR layouts.

Illustrative internal lowering of checked addition:

```text
fn example.add(%left: i64, %right: i64) -> i64 effects {} {
entry:
    (%value, %overflow) = checked.add.i64 %left, %right
    branch %overflow, overflow, done(%value)

overflow:
    fault IntegerOverflow

done(%sum: i64):
    return %sum
}
```

The model writes an addition. The compiler creates the overflow checks and control flow.

### 10.3 Native backend strategy

Start with explicit, inspectable textual LLVM IR emission for the scalar vertical slice and invoke a pinned LLVM toolchain. Move to an in-process API only when it delivers a measured build or maintenance benefit. This keeps the first backend easy to inspect without making textual IR a public GPT++ interface.

Verify emitted IR before optimization and again after transformations in development builds. Use checked-arithmetic intrinsics and guards for operations that require defined failure behavior.

LLVM has `poison`, undefined behavior, and operation-specific preconditions. Therefore, do not attach `nsw`, `nuw`, `inbounds`, purity, aliasing, or termination attributes unless the compiler has established their requirements. Integer division needs guards, and source-level purity is not sufficient to mark a runtime allocation call as having no machine-level effects. [R2]

Pin one LLVM release/build initially. A supported upgrade requires conformance, differential, sanitizer, and target-ABI testing; do not couple the implementation to an unpinned development branch.

### 10.4 Reference interpreter

The scalar bootstrap interprets the checked source tree so that an incorrect control-flow lowering can be detected by comparison with native execution. It bounds evaluation steps and nesting. As the language grows, a checked Core interpreter can replace this path if it preserves an independent semantic reference. It is used for tests, debugging, and differential comparisons against native output.

Sharing a frontend means interpreter/native agreement cannot detect every shared frontend bug. Complement it with hand-derived semantic tests, cross-language reference solutions, and independent acceptance oracles.

The interpreter is not a permanent substitute for native compilation. Native artifacts must be runnable without a source interpreter or model service.

### 10.5 Optimization policy

Implement straightforward constant folding, dead-code elimination where faults/effects permit it, inlining with budgets, specialization, and representation improvements. Add more ambitious fusion and escape analysis only after semantic tests and profiling justify them.

An optimizer must preserve result values, specified I/O ordering, and defined logical fault behavior. It need not preserve allocation count or identical resource-exhaustion points; that boundary must be explicit in the language specification.

Never use an LLM as an unverified optimization pass inside a normal build. An experimental model-proposed transformation can be evaluated outside the trusted build pipeline and admitted only through explicit validation.

### 10.6 Debugging and failures

Maintain source locations through all IR stages. Emit native debug information, symbol names, and structured fault records. Compiler errors should distinguish user errors from internal compiler failures. An internal error must fail closed, retain a minimized reproduction when authorized, and never emit a best-effort executable.

---

## 11. Runtime, memory, and interoperability

### 11.1 Managed memory is a deliberate trade-off

Choose a small, non-moving, stop-the-world tracing collector for the first managed runtime. Begin with explicit allocation metadata, precise root handles, and a simple mark/sweep algorithm. Optimize only after collection and rooting correctness are demonstrated.

This avoids asking AI authors to reason about borrowing and object lifetimes in every function, but it introduces runtime work, pause behavior, and a substantial trusted component. It is not a zero-overhead design and is unsuitable for hard-real-time claims.

In native code, live managed references must be visible at every allocation/call safepoint through explicit root slots or an equally validated mechanism. The compiler must protect roots against optimizer removal and handle temporaries, loop values, closures, and generic layouts correctly. LLVM's GC documentation describes compiler/runtime integration mechanisms; it does not supply a complete collector for GPT++. [R18]

### 11.2 Memory semantics and representations

Ordinary aggregates are immutable values. The runtime may share their storage, use persistent data structures, and specialize layouts. Source programs cannot observe internal object addresses or mutate through hidden aliases.

Recursive type layouts must include an indirection at recursive storage boundaries. The compiler rejects infinite-size unboxed layouts. The layout algorithm, pointer map, enum tag representation, and generic instantiation metadata are tested as runtime ABI components.

A prototype that keeps every allocation forever is acceptable only as an explicitly limited experiment, not as the managed runtime release. Heap reclamation, peak-memory tests, and exhaustion behavior are release gates.

### 11.3 Resource lifetime is not garbage collection

Files, sockets, and native handles require explicit resource semantics. Early library APIs should use scoped operations such as `fs.read_text` that open, operate, and close internally.

Before exposing long-lived handles, implement a scoped-resource construct with non-escape checking and deterministic cleanup on normal exits, early returns, and `?` propagation. A candidate form is `using resource = operation()? { ... }`. This is a separately gated extension, not an implied feature of the grammar sketch.

Cleanup must be non-throwing; operations where close/flush failure matters expose an explicit result-returning finish method. A process-aborting fault or forced termination cannot guarantee user-level cleanup. Transactional file updates must therefore use safe OS-level patterns rather than trusting finalizers.

### 11.4 Native interoperability

Use a documented C ABI for the first FFI. Export only fixed-width primitives, explicit byte spans, plain documented records, and opaque handles. Strings are not assumed to be null-terminated. Managed pointers do not cross the boundary without a registered handle/root and explicit lifetime policy.

FFI packages declare their imported symbols, effects, ownership rules, platform support, and native artifact hashes. They are trusted-code packages requiring admission; arbitrary native dependencies are not magically sandboxed by GPT++'s type system.

For the first FFI release, reject asynchronous callbacks and retained borrowed pointers. Support synchronous non-escaping calls, then add callbacks only after reentrancy, rooting, threading, and fault propagation are specified. No unwinding may cross the ABI boundary.

A Python bridge, JavaScript host adapter, or database driver may be built on these boundaries later. They are libraries/adapters, not alternative definitions of GPT++ semantics.

### 11.5 Concurrency after the sequential foundation

The proposed next profile uses structured tasks, explicit cancellation, immutable messages, and no unrestricted shared mutable state. Before accepting it, specify task lifetime, sendable types, capability delegation, cancellation points, cleanup, error aggregation, ordering, and how deferred effects appear in function/task types.

Do not add `async` syntax first and decide those rules afterward. The sequential 1.0 profile can serve requests synchronously or be deployed as multiple supervised processes; that is a scope boundary, not a concurrency implementation.

---

## 12. Standard library and packages

### 12.1 A small coherent library

| Group | Initial facilities | Design constraints |
|---|---|---|
| Core | Option/result utilities, tuples, assertions, comparison | Explicit error and equality rules |
| Collections | Lists, maps, sets, iterators | Specified order and documented complexity |
| Text | UTF-8 conversion, scalar iteration, formatting | No ambiguous character indexing |
| Numeric | Checked/wrapping arithmetic, parsing, math | Exact conversion and overflow rules |
| Data | JSON values, typed codecs, schema validation | Size/depth limits and deterministic diagnostics |
| Files | Restricted reads/writes and paths | Capability required; no ambient working-directory escape |
| Console | Input/output with typed errors | Explicit console authority |
| Time/random | Clock and random interfaces | Injected implementations for tests |
| Network | Synchronous HTTP and socket wrappers | Capability limits, explicit timeouts, bounded bodies |
| Testing | Unit/property tests, fixtures, fake host interfaces | Independent acceptance tests remain separate |

Do not invent task-specific primitives merely to make benchmarks shorter. Library additions need a general use case, documented semantics, and equivalent baseline-library access in comparative evaluations.

### 12.2 API metadata generated from checked code

Every public symbol exports its name, type, effects, documentation, error variants, stability level, examples, and capability requirements. The compiler generates these from checked declarations and registered library metadata; humans should not maintain a conflicting duplicate API definition.

Natural-language documentation is helpful but not executable authority. An agent must receive the actual signature and schema alongside prose. Package versions and interface hashes accompany every retrieved API.

### 12.3 Package management

Use a TOML manifest and a content-addressed lockfile. Initially support vendored local packages and a reviewed package catalog; a public registry is not needed to prove the language.

Dependency resolution is a separate explicit network-enabled action. Normal checking, testing, and building use pinned local artifacts and fail when a required artifact is missing. No opportunistic package installation during compilation.

Build scripts, native plugins, and compiler extensions are disabled by default. An approved exception runs in a constrained build environment with declared inputs and outputs. Package signatures establish origin/integrity, not code safety.

### 12.4 Preventing invented APIs

The agent context includes an allowlisted symbol inventory for installed dependencies. Unknown imports and unresolved members produce concise diagnostics with available candidates. Suggestions do not install packages, mutate lockfiles, or choose semantically similar APIs automatically.

A dependency addition is a separate reviewed operation because it changes trust, supply-chain exposure, licensing obligations, and potentially runtime behavior.

---

## 13. The AI authoring protocol

### 13.1 Core interaction loop

```text
Read task and permitted change scope
    -> request compiler-derived context
    -> propose a bounded patch
    -> validate patch structure and revision
    -> check the changed program
    -> run permitted tests in isolation
    -> inspect compact diagnostics
    -> repair within the same budget and authority
    -> commit only an accepted transaction
```

The compiler does not need to know which model proposed the patch. The protocol also works with an editor or a deterministic code transformation.

### 13.2 Context bundles

`gpp context` constructs the information relevant to a named symbol or task scope: its current body/signature, referenced types, imported signatures, effect limits, applicable contracts, local tests, selected callers, compiler edition, dependency versions, and policy constraints.

Signature-only context is not always sufficient. Include implementation bodies when the task depends on undocumented behavior, aliasing assumptions, performance characteristics, or a suspected implementation bug. Report unresolved dependencies and omitted relevant material rather than representing an incomplete bundle as complete.

Cache the stable interface portion separately from the changing body and diagnostics. Token-budget trimming must retain mandatory semantic context. If that is impossible, return `context_incomplete` with the missing categories and let the authoring system request a wider budget or narrower change.

Illustrative context envelope:

```json
{
  "protocol": "gpp.agent/1",
  "revision": "sha256:<repository-snapshot>",
  "target": "example.users.adult_names",
  "edition": "1",
  "signature": "fn adult_names(users: List<User>) -> List<String> !{}",
  "types": {
    "User": {"name": "String", "age": "I64"}
  },
  "allowed_effects": [],
  "public_api_change_allowed": false,
  "dependency_interfaces": ["sha256:<std-list-interface>"],
  "included_test_ids": ["adult_names_boundary_and_order"],
  "completeness": "complete_for_declared_scope"
}
```

Angle-bracket strings in protocol examples are placeholders. Production messages contain validated hashes and actual structured signatures; the compact string form here is for readability.

### 13.3 Transactional patches

Initial patch operations are `add_declaration`, `replace_body`, `update_signature`, `rename_symbol`, and `remove_declaration`. Implement `replace_body` first. Signature changes and dependency/capability changes require explicit permissions distinct from ordinary body edits.

Illustrative request:

```json
{
  "protocol": "gpp.agent/1",
  "request_id": "change-0042",
  "base_revision": "sha256:<repository-snapshot>",
  "operations": [
    {
      "op": "replace_body",
      "symbol": "example.users.adult_names",
      "expected_signature_hash": "sha256:<signature>",
      "expected_body_hash": "sha256:<old-body>",
      "body_source": "{ var names: List<String> = []; for user in users { if user.age >= 18 { names = list.push(names, user.name); } } return names; }"
    }
  ],
  "policy": {
    "allow_public_api_change": false,
    "allow_dependency_change": false,
    "allow_capability_expansion": false,
    "allow_acceptance_test_change": false
  },
  "required_checks": ["parse", "type", "effects", "unit_tests"]
}
```

The tool validates schema and limits, compares snapshot/signature/body hashes, applies the edit in a temporary snapshot, checks dependent symbols, runs permitted checks, and commits atomically only if the transaction passes. On failure, the original working tree remains unchanged and the candidate is available for inspection.

Multi-symbol patches are one transaction. A stale patch is rejected, not fuzzily applied. An explicit rebase tool can obtain current context and request a new patch; it must not silently reinterpret old intent.

**Implemented scalar maintenance operations.** The compiler can replace a target body while preserving its declaration and checked callers. The model-facing tool can also insert native statements before the original body or lower a typed list of ordered exceptions. Supplying public examples enables a bounded validation loop. A failed caller assertion can supply either a bounded excerpt or one exact target value derived from the unchanged caller's arithmetic. The latter is available only when the result determines a unique integer at one concrete argument tuple and a checked replay confirms it. [Maintenance preset](../tools/README.md) · [Caller analysis](../tools/caller_obligation.md)

### 13.4 Symbol identity

Use fully qualified symbol names plus signature/body hashes initially. Names remain stable across body edits; renames are explicit operations that update references atomically. Internal node identifiers are snapshot-local, and the protocol must say so.

An optional persistent identity index may assist moves/renames later, but it must not create a hidden second source of program semantics. Reconstructible indexes belong in caches, and any required persistent metadata belongs in version control.

### 13.5 Protocol transport

Provide a versioned JSON-RPC service over standard input/output and ordinary CLI equivalents. No listening network service is needed by default. Requests have size limits, deadlines, revision IDs, explicit workspace roots, and structured responses.

Keep editor integration compatible with established Language Server Protocol concepts, but expose richer agent operations as a separately versioned protocol rather than overloading unrelated editor requests. [R16]

### 13.6 Optional constrained generation

Export a syntax grammar and source-AST JSON Schema. Integrate an existing grammar engine, such as XGrammar or llguidance, through adapters rather than implementing token masking from scratch in the compiler. These projects provide grammar/structured-generation infrastructure; their published performance claims are not GPT++ performance results. [R14][R15]

Closed model services may not expose arbitrary token masking. Support three modes: plain source plus compiler feedback, schema-constrained patch output when available, and grammar-constrained generation on compatible inference systems.

Type-aware token constraints are an experiment after ordinary compiler-guided repair works. Include timeout, dead-end, and fallback handling. Research on constrainer alignment is a reason to measure acceptance and latency rather than assuming that the strictest decoder is best. [R6]

---

## 14. Diagnostics and repair

### 14.1 A diagnostic is an interface

Every diagnostic has a stable code, severity, category, source location, owning symbol, concise explanation, machine-readable evidence, related locations, and optional repair alternatives. It must distinguish a proved fact from a heuristic suggestion.

Illustrative type mismatch:

```json
{
  "schema": "gpp.diagnostic/1",
  "code": "GPP-TYPE-001",
  "severity": "error",
  "symbol": "example.math.divide",
  "location": {
    "file": "src/math.gpp",
    "start_byte": 412,
    "end_byte": 438
  },
  "message": "Return value has the wrong type.",
  "expected": "Result<I64, DivideError>",
  "actual": "I64",
  "repair_options": [
    {
      "kind": "wrap_in_ok",
      "precondition": "The value represents successful division."
    }
  ],
  "automatic_fix_safe": false
}
```

Positions are UTF-8 byte offsets internally. Editor adapters translate to the negotiated position encoding; they must not confuse bytes, Unicode scalars, and UTF-16 code units.

### 14.2 Repair-friendly behavior

Group cascading errors under their root causes, preserve deterministic ordering, and return a compact summary with expandable details. Include a type mismatch's relevant declarations rather than the entire file. For effect violations, identify the call introducing the extra effect and the caller's allowed set.

A proposed repair must not quietly change a public return type, suppress a test, grant filesystem/network access, convert a checked operation into an unchecked one, or weaken a contract. Such changes require explicit authorization and an explanation of the behavioral change.

Avoid repetitive compile/retry loops by recording attempted patches, unchanged diagnostics, and budget use. Stop when the repair budget is exhausted, report the unresolved problem, and leave the accepted tree intact.

### 14.3 Diagnostic quality tests

Maintain regression fixtures for stable codes, correct locations, causal grouping, and concise output. Measure whether each diagnostic reduces successful repair cost in controlled tasks. A plausible natural-language message is not sufficient if it routinely drives the model toward the wrong fix.

---

## 15. Contracts, testing, and verification

### 15.1 An explicit assurance ladder

| Level | Evidence produced | Limitation |
|---|---|---|
| Parsed | Valid source structure | Names and behavior may still be wrong |
| Checked | Type, match, and effect rules satisfied | Does not establish intended behavior |
| Runtime-guarded | Checks fail on exercised violations | Unexercised paths remain |
| Tested | Independent examples/properties pass | Coverage is finite |
| Exhaustively checked finite contract | The scalar interpreter evaluated the predicate successfully on every declared input | The predicate and domain determine the guarantee |
| Verified subset | Supported obligations proved under listed assumptions | Does not cover unsupported features or mistaken requirements |
| Audited | Human/security review of important boundaries | Review can miss defects |

Do not collapse these states into a badge called “correct.” Reports must identify what was checked, by which tool/version, against which source, under which assumptions.

### 15.2 Testing architecture

Support pure unit tests, bounded property tests with shrinking, fuzzing, and integration tests with fake capability implementations. Time, randomness, filesystem state, and network behavior must be injectable where the test needs determinism.

Keep author-visible tests separate from sealed acceptance tests. An AI may add useful tests but must not be able to redefine the oracle to match its implementation. Generated tests require review or independent validation when they become acceptance criteria.

The compiler/runtime test suite includes parsing negatives, type/effect negatives, enum exhaustiveness, arithmetic boundaries, UTF-8 errors, large nesting, recursion limits, generic expansion limits, GC stress, FFI layout, capability denials, and platform behavior.

### 15.3 Proposed solver-based verification

Start with scalar arithmetic and branching contracts, then consider bounded collection properties. Use a solver adapter with explicit time/memory limits and four distinct outcomes: `proved`, `refuted`, `unknown`, and `unsupported`.

Machine integers require bit-vector or otherwise justified bounded-arithmetic encodings; mathematical integer proofs cannot silently justify fixed-width operations. Every generated obligation carries source provenance and the assumptions used.

A `proved` status is relative to the translation, solver, and trusted implementation. Do not call it an independently checked proof certificate unless a certificate checker actually exists. Dafny's documentation is a useful reference for contract/verification design, but GPT++ needs its own correct semantics and translation. [R10]

### 15.4 Proposed solver modes

`gpp verify --mode=report` reports supported obligations and leaves runtime checks intact where needed. `--mode=required` fails on any unproved required obligation, including `unknown`; it must not reinterpret solver timeouts as success.

A proof cache key includes source/core IR, contracts, dependencies, arithmetic model, solver version/options, compiler version, and assumptions. Unsupported FFI behavior is an explicit trusted assumption or a reason to reject verification.

---

## 16. Security and execution policy

### 16.1 Threat model

Treat model-generated source, patches, package metadata, test inputs, dependency documentation, and native libraries as potentially hostile. Protect the user's files, credentials, network, compute budget, repository history, and acceptance criteria.

The trusted computing base includes the compiler, runtime, package verifier, sandbox/host, allowed native dependencies, and applicable solver machinery. It is not eliminated by using a safer source language.

### 16.2 Three distinct enforcement layers

**Language checks** control legal program structure and declared behavior. **Capability enforcement** restricts approved host operations. **Execution isolation** limits what a compiled or interpreted process can do if generated code, dependencies, or an implementation defect cross a boundary.

An effect set is not a sandbox. Native code and arbitrary FFI can bypass language-level conventions unless an external enforcement boundary restricts the process. WASI and Wasmtime provide useful capability-based precedents, but their existence does not make a GPT++ native executable isolated. [R13]

### 16.3 Safe execution defaults

Run untrusted evaluation in disposable environments with explicit CPU, wall-time, memory, process, filesystem, output-size, and network limits. No inherited credentials, SSH agents, cloud metadata access, or writable host project mounts. Start with no network and only copied fixtures.

`gpp test --sandbox` must fail if the requested guarantees cannot be enforced on the host. It must not silently fall back to unrestricted native execution. Platform adapters need their own tested policies; a Linux container configuration is not automatically a macOS or Windows sandbox.

Trusted local development can offer an explicitly acknowledged unsandboxed mode. Mark its status in logs and do not use it for untrusted benchmark samples.

### 16.4 Capability details that require tests

Filesystem policies must resist traversal, symlink escape, and time-of-check/time-of-use races. Network policies need explicit DNS, redirect, loopback, private-address, and proxy handling. Process execution needs executable/argument rules and must not default to shell-string evaluation.

Revocation and delegation rules must be documented. Passing a capability to a helper delegates authority to that helper; declaring a function pure must prevent calling effectful capability operations but does not erase possession of the value.

### 16.5 Supply-chain and authoring safety

No automatic dependency installation, public-API widening, capability expansion, or acceptance-test deletion is part of normal repair. Retrieval of package documentation is untrusted content, not an instruction to execute commands. The agent can propose an action; a policy layer determines whether it may execute.

Provide an audit trail of accepted changes, dependency additions, permission changes, tool invocations, and validation results. Record model identifiers when available, but never store private prompts, secrets, or credentials merely for analytics without explicit policy.

---

## 17. Incremental builds and reproducibility

### 17.1 Dependency-aware compilation

Cache lexing/parsing by source content, resolution by module/import graph, checking by body plus interface dependencies, and code generation by checked IR plus target/runtime/backend settings.

A signature-stable body change can avoid rechecking unrelated modules, but inlined code, compile-time constants, generic specializations, and verification assumptions can create body-level dependencies. Track those dependencies rather than using the false rule that signatures are always sufficient cache keys.

Suggested cache identity:

```text
hash(
    semantic_input,
    relevant_dependency_interfaces_and_bodies,
    edition,
    compiler_build,
    runtime_abi,
    backend_build,
    target_and_sysroot,
    optimization_options,
    applicable_policy_and_verification_assumptions
)
```

Source maps and documentation can require updates even when executable semantics are unchanged. Keep those artifacts correctly keyed as well.

### 17.2 Reproducible builds

Pin dependencies, runtime, compiler, LLVM, linker, and target SDK/sysroot. Control timestamps, path remapping, locale, environment inputs, archive ordering, and build-generated identifiers. Reproducibility is tested on specified environments, not asserted from deterministic parsing alone.

Separate `fetch` from `build`. Release builds must succeed from a prepared offline cache. If the build depends on a native dependency or platform SDK, capture its identity and support/license conditions in the build manifest.

### 17.3 Reproducible AI experiments

Record prompts, language-guide versions, tool responses, model identifiers, available model build details, decoding configuration, seeds where supported, tokenizer versions, context-cache state, and all budgets. Model-service drift limits exact reproducibility; disclose it rather than treating repeated provider names as identical models.

---

## 18. Model adaptation and training data

### 18.1 Support existing models before training a new one

The first authoring mode supplies a concise language guide, compiler-generated API context, worked examples, and diagnostics to an unchanged code-capable model. Keep the language guide versioned and small enough to test its actual context cost.

Provide separate task-specific examples rather than injecting the entire specification into every request. A function-writing task should not receive FFI documentation unless the task needs it.

A model that only works after extensive custom training might still be useful, but that is a different deployment proposition. Report unchanged-model and adapted-model results separately.

### 18.2 Data curriculum

| Stage | Material | Admission requirements |
|---|---|---|
| Seed | Human-reviewed examples for each language rule | Compiles, executes, and has independently checked expectations |
| Translation | Equivalent tasks in GPT++ and established languages | Shared input/output semantics and differential tests |
| Composition | Multi-module programs using real interfaces | Dependency isolation, integration tests, API consistency |
| Repair | Incorrect program, diagnostic, minimal successful fix | Real checker output and regression tests |
| Maintenance | Existing project, requested change, accepted patch | Unrelated behavior retained; change scope respected |
| Security | Capability misuse and unsafe suggestions | Rejection or safe implementation verified independently |
| Performance | Competing implementations with equivalent behavior | Measured execution and generation costs, not guessed rankings |

MultiPL-T provides a relevant precedent for using tests to filter translated training examples. GPT++ should adopt the validation principle, not assume that any generated translation is reliable. [R7]

### 18.3 Dataset integrity

Store source provenance, license, generator/model details where allowed, compiler version, test hashes, and validation results. Deduplicate by task family, algorithmic structure, and source lineage—not just exact text. Split entire repositories and related task variants across train/development/evaluation partitions.

Do not use sealed acceptance tests in prompts or repair trajectories. Do not fine-tune on compiler bugs or a solution that passes only because the language implementation is wrong. Regenerate or revalidate the corpus when semantics change.

A generated explanation should not be treated as a proof. Execution traces and actual diagnostics are more reliable training signals than unverified prose describing why code ought to work.

### 18.4 Adaptation sequence

Begin with in-context examples and retrieval. Then test supervised adaptation of an open-weight model with a documented, licensed dataset. Compare against an equally resourced adaptation effort for the strongest existing-language baseline.

Prioritize source generation, structured edits, diagnostic interpretation, and minimal repairs. Do not simultaneously change model architecture, tokenizer, syntax, library, and training corpus and then attribute all gains to the language.

Custom vocabulary/tokenizer work is a late research track. New tokens need compatible model adaptation, and ordinary hosted model APIs do not become fluent in a new encoding merely because a compiler supports it.

### 18.5 Human review is part of the system

Generate ordinary formatted source and meaningful diffs for accepted changes. Expose contracts, permissions, dependencies, test results, and API changes to reviewers. AI-oriented authoring must not force humans to approve opaque numeric instruction streams.

---

## 19. Evaluation and success criteria

### 19.1 Research question

At equal task requirements and bounded resources, which workflow produces more correct changes? What does each accepted change cost in model usage, tool time, feedback and review, and how does the resulting program perform?

This question has two distinct answers to measure: the benefit of the **language** and the benefit of the **language plus tooling**. A good agent protocol should not be misreported as proof that a new syntax was necessary.

The first scalar pilot completed 72 matched trials on 12 tasks with two local models. GPT++ accepted 0 of 24 submissions, Rust accepted 0 of 24, and typed Python accepted 3 of 24. GPT++ consumed 44.5% more total tokens than Python and 15.3% more than Rust. Eighteen GPT++ submissions ended with syntax errors. GPT++ and Rust had no finite token cost per accepted submission in that pilot. Further testing should first establish a baseline with enough accepted work to compare cost per accepted change. [Pilot report](../bench/empirical/results/2026-11-19.md)

In a fresh 64-trial study, supplying a fixed declaration and asking for one edit raised GPT++ acceptance from 1/16 to 4/16 on identical task/model pairs. Typed Python accepted 8/16 and Rust accepted 4/16. GPT++ fragments consumed 3.32 times the tokens per accepted change of typed Python, with a paired 95% interval of 1.20–13.35. Correctness remained the main cost driver. Nine of twelve terminal GPT++ fragment failures produced the wrong answer. Require behavioral checks on model-authored edits whenever examples are available. [Paired fragment results](../bench/iterate/results/paired.md)

A second study ran 40 matched trials with Qwen2.5-Coder 7B on eight different tasks. Native GPT++ infill, typed Rust infill and a restricted Python-to-GPT++ input each accepted 0/8. GPT++ chat accepted 1/8 and typed Python infill accepted 4/8. Inspection showed both missing scalar operations and generation continuing past the intended function. Replaying identical saved text after implementing checked integer `abs`, `min` and `max` recovered one task. Evaluate model-side stopping prospectively in each language before attributing costs to syntax. [Infill results](../bench/iterate/results/infill.md) · [Same-output replay](../bench/iterate/results/projection-replay.json)

The prospective boundary-stop study completed all 56 assignments. Stopping at the function boundary cut native GPT++ token use by 14.5% and acceptance stayed at 1/8. Rust rose from 1/8 to 3/8 with the same intervention. Stopped typed Python accepted 4/8 at 765 tokens per accepted change, compared with 4,481 for native GPT++. The revised Python-syntax input to GPT++ accepted 1/8 at 4,272 tokens. [Boundary-stop results](../bench/iterate/results/boundary.md)

**Decision after the three follow-ups.** Keep revision-guarded edits, example-based validation, and bounded generation. The scalar data justify those implementation choices but give no basis for advancing to a large qualification run or investing in a new tokenizer. Move the next development comparison to changes in existing programs with multiple callers. Measure the cost of finding the right function, generating the change and preserving caller behavior. Give typed Python and Rust equivalent local context, scoped edits, public feedback and stopping rules. Freeze the comparator, task families and a monetary or compute cost model before making a comparative cost claim.

**Multi-caller maintenance result.** Eight authored scalar reproductions of documented application changes and standards produced 40 matched trials on Qwen2.5-Coder 7B. With the same caller selection, GPT++ accepted 4/8 at 1,850 tokens per accepted edit, typed Python accepted 6/8 at 760.33, and Rust accepted 3/8 at 2,124.33. GPT++ used 12.9% fewer tokens per accepted change than Rust in this comparison. GPT++ used 2.43 times Python's tokens per accepted edit. A GPT++ control omitted caller excerpts and retained caller examples and tests. It accepted 4/8 with 1,325.50 tokens per accepted edit. Keep excerpts opt-in and validate through callers whenever cases are available. This benchmark supplied the target location, so repository navigation remains a separate experiment. [Multi-caller benchmark](../bench/maintenance/README.md)

**Caller context triggered by a public failure.** A fresh 40-trial run on eight other tasks gave adaptive GPT++ 2/8 at 2,955.50 tokens per accepted edit, typed Python 3/8 at 1,608, and Rust 1/8 at 6,346. Adaptive GPT++ ranked between typed Python and Rust on both observed acceptance and tokens per accepted edit. The eight-task sample leaves substantial uncertainty. Five GPT++ retries received caller excerpts after a caller failure and none passed. The target-only control accepted the same two tasks at 2,595 tokens per accepted edit. Keep the trigger opt-in and retain caller validation regardless of prompt mode. [Adaptive benchmark](../bench/adaptive/results/adaptive.md)

**Maintenance qualification status, 20 November 2026.** The next 154 paired assignments used two models on eight decision-policy fixtures and three historical upstream changes. A separate 15-call intervention reused the first failed outputs to isolate the value of exact target feedback. The studies report native replacement, protected insertion and ordered rules separately, including one-shot costs, zero-success arms, tokenization and offline replay. The current plan uses these results in Sections 1 and 20. [Complete maintenance report](../bench/policy/README.md)

**Expression-level maintenance.** On three new upstream scalar fixes, a 72-trial experiment compared whole bodies, supplied expression ranges and two ways to ask the model to find a site. The prespecified Qwen locate-and-edit workflows accepted zero changes in GPT++, typed Python and Rust. With the correct site supplied, StarCoder2 repaired Redis in GPT++ and Rust at 908 and 897 tokens per accepted edit respectively across the three tasks. A follow-up exposed each syntax node under a numbered ID. All 18 model calls selected a real node, and zero changes passed all behavioral checks. Prioritize locating the faulty computation using public execution values and guiding the replacement with its expected type. [Results and limitations](../bench/expression/README.md) · [Next milestone](../ROADMAP.md#next-milestone)

### 19.2 Baselines and controls

Use Python with type checking and tests, TypeScript with strict checking and tests, and Rust with its normal compiler/test tooling. Pin the actual tools and configurations at experiment execution; do not compare against an intentionally weak prompt-only baseline.

For each language, provide the strongest practical equivalent of context retrieval, API documentation, incremental edits, structured diagnostics, and the same test/repair budget. Native patching facilities differ, so document residual differences rather than claiming perfect parity.

Run a tool-ablation study: ordinary source workflows, enhanced existing-language workflows, GPT++ text-only, and GPT++ with the complete proposed authoring protocol. Where possible, expose an existing language through the same patch/context harness to isolate tooling from syntax.

Do not give GPT++ a prewritten library solution while requiring another language to recreate it. Equivalent standard/package functionality must be available, or the experiment must identify the ecosystem difference it is measuring.

### 19.3 Task corpus

Grow the development suite toward 120 tasks after the scalar pilot, then use a disjoint qualification suite provisionally sized at 600 tasks. These counts are proposed planning sizes, not a guarantee of statistical power.

| Qualification category | Tasks | Important checks |
|---|---:|---|
| Algorithms and data structures | 100 | Edge cases, complexity, recursion, overflow |
| Parsing and data transformation | 100 | Unicode, malformed inputs, ordering, schema errors |
| I/O and service behavior | 80 | Timeouts, partial failures, capability restrictions |
| Multi-module changes | 140 | Public API stability, dependency context, regressions |
| Bug diagnosis and repair | 100 | Correct root cause, minimal fix, retained behavior |
| Security/error-path hardening | 80 | Rejected authority expansion, realistic failure paths |
| **Total** | **600** | |

Represent realistic maintenance, not only isolated algorithm puzzles. Add a smaller human-review study on diffs and understandability; do not use a model's own preference score as the sole maintainability measure.

Tasks must define numeric ranges, Unicode behavior, ordering, error semantics, permitted dependencies, and runtime limits identically across implementations. Python's numeric behavior, for example, cannot be assumed equivalent to fixed-width GPT++ arithmetic without explicit task constraints.

Use independent executable oracles, boundary tests, property/metamorphic checks, and reviewed reference implementations. Existing benchmarks can inform evaluation design, but translated tasks need validation and license checks. EvalPlus and LiveCodeBench motivate stronger oracles and multiple coding scenarios, not automatic comparability after translation. [R11][R12]

### 19.4 Model cohorts

Test at least three model configurations spanning a smaller local/open-weight model, a stronger open-weight model, and a hosted model when available. Select and record exact versions at run time rather than freezing this design to a product list that will age.

Evaluate unchanged models first. Run adapted-model experiments separately with matched training budgets and dataset accounting. Use repeated trials and task-level analysis; multiple completions of the same problem are correlated, not independent new problems.

### 19.5 Experimental protocol

For each run, fix the task specification, public tests, maximum model calls, input/output budget, wall-time limit, permitted tools, dependency set, and execution limits. Use one initial attempt plus at most three repair attempts as the initial protocol, subject to the overall budget.

Repair sees only allowed compiler diagnostics and public test feedback. Sealed acceptance tests are used by the evaluator after the run, not as a hidden iterative oracle supplied to the model.

Measure cold sessions and warmed/cached sessions separately. Include language-guide setup cost, grammar compilation/masking, and tool round trips. Run both constrained and unconstrained generation where supported. Count decoder dead ends and tool failures as workflow failures.

Use paired tasks, randomized condition order, and task-clustered confidence intervals. Bootstrap by task/repository family, not by treating every repair as a separate sample. Pre-register the main acceptance/cost comparison and account for multiple exploratory comparisons.

Do not use `pass@k` to label a feedback-driven repair process. Report first-attempt success separately from success within a fixed interactive budget.

### 19.6 Metrics to publish

| Metric | Definition or requirement |
|---|---|
| First-attempt acceptance | Fraction passing the independent oracle without repair |
| Budgeted acceptance | Fraction passing within the fixed workflow budget |
| Cost per accepted task | Includes failed tasks and all attempts |
| Input/output tokens | Actual measured usage by model/tokenizer |
| Latency | End-to-end median and tail, with cold/warm separation |
| Repair behavior | Calls, edits, recurring diagnostics, rejection reasons |
| Change isolation | Unrelated changed symbols and behavior regressions |
| Permission safety | Unauthorized grants/operations and policy-bypass attempts |
| Runtime | Execution time, memory, allocation behavior, startup, artifact size |
| Reviewability | Human review time and defect detection on matched changes |
| Compiler reliability | Crashes, miscompilations, invalid acceptance, hangs |

Report complete failure categories. Do not discard difficult tasks from one condition after seeing its output.

### 19.7 Evidence for comparative claims

Select comparators and budgets on development data, then freeze them before qualification. State the question being tested. A claim about faster validation uses identical checked inputs and compares elapsed time and outputs. A claim about more effective agent repairs uses paired tasks, model configurations and independent behavioral oracles.

**Correctness.** Publish first-pass and final accepted counts, their denominators and paired differences against each comparator. Include failing, abstained, invalid and timed-out runs. Estimate uncertainty across independent tasks or repository families and check whether the result holds across model configurations.

**Cost and latency.** Report input and output tokens, calls, retries, tool work, elapsed time and external information obtained. Calculate tokens per accepted task only for workflows with at least one accepted task. When either side has zero accepted tasks, the comparison of that ratio is undefined. Preserve total costs and acceptance counts in those cases.

**Operational quality.** Run conformance and negative tests for the published profile. Measure application runtime and memory on the declared platform. Test interface-preserving changes through unchanged callers. Record regressions, unrelated changes and the work a reviewer must perform.

A comparative result should name the observed advantage and its limits. Faster compiler checks, fewer model tokens and more correct edits answer different questions.

### 19.8 Evaluation cost containment

A full illustration with 600 tasks, three models, four primary conditions, and three repetitions produces 21,600 task-runs. With up to four model calls per run, the ceiling is 86,400 calls before additional ablations. These are planning arithmetic, not required spending.

Use staged experiments: development pilot, focused ablations, then qualification. Abort clearly dominated variants early using a documented rule; do not repeatedly inspect sealed results and silently tune to them. Retain fresh holdouts after substantial design changes.

### 19.9 Required ablations

Test explicit effects on/off in context, explicit versus inferred local types, descriptive versus compact local names, whole-file versus symbol patches, plain text versus source AST, signatures-only versus richer context, grammar constraints on/off, and adaptation on/off.

Record actual token savings before making syntax changes. If most savings come from patching and context extraction, prioritize those features and avoid adding complexity solely to make GPT++ appear more novel.

---

## 20. Implementation roadmap

The roadmap is dependency- and evidence-driven. Version labels are planned milestones, not published software or calendar commitments.

### Active decision gate for maintenance

The scalar compiler, interpreter, native backend and scoped editor already run. Phase 0 now concerns the mechanism that saves an LLM work. New authoring features need a failing example from a logged attempt, a semantics-preserving implementation, an edit of equivalent scope in strong baseline languages and a fresh paired experiment. Record model and tool costs separately. Version the evaluation surface so that previous experiments still replay.

1. Establish that each task is expressible. Run independently written rule patches through the same compiler and hidden caller tests as generated patches.
2. Compare whole-body replacement, protected native insertions and typed rule insertions under the same public contract. Separate first-call results from the cost and yield of caller-triggered repair.
3. An ablation on all 15 eligible caller retries found that substituting a derived target result reduced retry tokens by 24–26%. Both variants recovered zero edits. Spend further effort on the initial edit and distinguishing boundary conditions. [Matched alternate retries](../bench/policy/results/retry-obligations.md)
4. Test transfer using actual historical code changes and identifiable consumers. Track the work lost in extracting or porting each case and report any gap to full-repository maintenance. Expand beyond scalar decisions before a general language claim.
5. Select each language's strongest combination of edit surface **and retry policy** on development data before the next qualification run. Compare against a one-shot baseline whenever retries recover few or zero edits. On the Qwen policy tasks the same five Rust edits cost 465 tokens each with one call and 783.40 with caller-triggered retries. This choice reverses the observed GPT++ versus Rust ordering.
6. Ship operations with reproducible correctness evidence and state their limits. For a comparative cost claim, evaluate against a frozen baseline on fresh work and publish the measurements and paired uncertainty described in Section 19.7. Use observed authoring failures to decide which information or operation the language should expose next.

### Phase 0 — Establish the experiment and semantic contract

**First deliverables.** Write a scalar language card, hand-derived value and fault fixtures, and a public development task with the same acceptance cases for GPT++ and existing languages. Build the small native slice in Section 27 across Phases 1 and 2 before expanding either phase. The 120-task corpus can grow alongside this work.

The first public calibration changes a member shipping threshold in GPT++, Python, and Rust. Its oracle checks both the new threshold and preserved checkout behavior. [Calibration task](../bench/pilot/README.md)

**First authoring pilot.** After scalar conformance, run a small paired development set of fresh implementations and maintenance changes. Start with pure functions over bounded integers. Use common inputs, edge-case oracles, and the same model version, call ceiling, context policy, and repair budget across GPT++, typed Python, and Rust. Include setup and guide tokens even on a failed attempt. Record every assigned task, its acceptance, usage by call, tool time, and failure reason. Execute model-authored submissions under the isolation rules in Section 16.

**Decision after the pilot.** Check that each oracle catches intentionally incorrect solutions and that usage and acceptance are available for every assigned condition. Use the cost breakdown to choose the next experiment. If retrieval or patch size dominates, test the same tooling on an existing language before expanding GPT++. If essential tasks cannot be expressed, add the smallest missing feature required by those tasks. Small public samples guide engineering and pilot sizing. Qualification uses fresh task families, a locked comparator and the reporting criteria in Section 19.7.

**Scalar workflow now implemented.** The compiler owns the declaration and validates replacement expressions or statement lists. It can preview the edit and apply it against a source revision. The local proposal tool accepts behavioral examples, runs them on the checked proposal, and can send a failing input back for one repair. This brings the single-function part of Phase 3 forward. Multi-module edits and the larger language features still have their own exit criteria. [Working editor](../tools/README.md) · [Paired studies](../bench/iterate/README.md)

**Work:** compare two or three concrete syntax variants using token measurements and limited executable prototypes. Decide the baseline syntax, arithmetic behavior, effect notation, mutation rules, and package/interface boundaries. Establish which properties cannot yet be measured before executable semantics exist.

**Exit gate:** every claimed advantage is tied to a metric; the first vertical slice is specified; no essential decision is deferred behind the phrase “AI will handle it.” Token-count experiments alone cannot pass a behavioral-efficiency claim.

### Phase 1 — Executable core, proposed v0.1

**Deliverables:** lexer/parser/formatter; name/type checker; scalar and aggregate values; explicit functions; local variables and control flow; records/enums; `Option`/`Result`; initial collections; simple generic specialization; effect checking; reference interpreter; pure unit tests; machine-readable diagnostics.

Implement in thin slices. Start with scalar functions and returns; add loops, then aggregates and error types. Add an injected console capability for a real entry point rather than hidden interpreter I/O.

**Exit gate:** positive and negative conformance suites pass; examples execute under the interpreter; type/effect errors have stable codes; no incomplete syntax is accepted as a runnable program. The implementation is clearly identified as an interpreter-backed frontend at this stage.

### Phase 2 — Own native compiler, proposed v0.2

**Deliverables:** GPT++ Core/MIR; IR verifiers; LLVM lowering; object emission and linking; checked arithmetic; managed runtime and root protocol; native entry point; debug/source information; initial macOS ARM64 and Linux x86-64 support.

Build the first scalar native executable before adding managed collections to the backend. Then port the checked semantic subset systematically and stress-test garbage collection.

**Exit gate:** supported conformance programs agree across interpreter and native execution; native artifacts run without the interpreter or an LLM; arithmetic and GC stress tests pass; release and debug behavior agree where the specification requires it.

### Phase 3 — Practical language and AI editing, proposed v0.3

**Deliverables:** modules and generated interfaces; locked local packages; JSON codecs; restricted filesystem APIs; application capabilities; context extraction; atomic `replace_body` patches; revision checks; diagnostic repair loop; basic editor integration.

Add other patch operations only after transactional body edits work. Turn the hello/data-transformation examples into executable documentation and establish scoped host-resource APIs.

**Exit gate:** an agent changes a real multi-module program using limited context without weakening tests, changing unauthorized APIs, or expanding capabilities; rejected/stale patches do not mutate the accepted tree.

### Phase 4 — Assurance and empirical qualification, proposed v0.4

**Deliverables:** contracts with runtime checks; property/fuzz testing; capability-negative tests; benchmark accounting; model-adapter interfaces; constrained-generation adapters; optional bounded solver support; independently reviewed translation data.

Run existing-language controls and ablations. Treat advanced type-constrained decoding, tokenizer modifications, and extensive fine-tuning as optional research tracks, not blockers for understanding the base language.

**Exit gate:** reproducible evidence of costs and failure modes; no claims of proof from tests; implementation quality sufficient for the qualification experiments; a decision on whether syntax and tooling have earned further investment.

### Phase 5 — Production hardening and 1.0 candidate

**Deliverables:** complete sequential profile documentation; reviewed synchronous network APIs; scoped resource handling; restricted C-ABI interop; Windows x86-64 port; package provenance; reproducible offline builds; upgrade policy; security reporting; all demonstration applications.

**Exit gate:** the definition of done in Section 26 passes. Publish supported target/profile combinations, known limitations, benchmark artifacts, and the outcomes and uncertainty for each comparison.

Do not call the language production-ready simply because the examples compile or because the compiler has been rewritten in GPT++.

### After 1.0 — Earned extensions

Prioritize extensions according to actual application demand: a stable WASI target, structured concurrency, effect-polymorphic APIs, richer interoperability, additional numeric domains, profiling-guided optimizations, and stronger verification.

Self-hosting and a dedicated model/tokenizer are optional long-term projects. They must not displace runtime correctness, library usefulness, or measurement of the original efficiency thesis.

### Dependency summary

```text
Semantics + test harness
    -> frontend + interpreter
    -> typed IR + native scalar slice
    -> paired scalar authoring pilot and scope decision
    -> managed native runtime for selected aggregate workloads
    -> practical modules/stdlib
    -> safe patch/context workflow
    -> qualification and hardening
    -> sequential 1.0
    -> advanced targets/concurrency/model specialization
```

Some harness and tooling work can proceed in parallel. Native collection support still depends on runtime/root correctness, and public efficiency claims still depend on independent experiments.

---

## 21. Repository and engineering workstreams

### 21.1 Proposed repository

```text
gptpp/
  README.md
  LICENSE
  SECURITY.md
  CONTRIBUTING.md
  Cargo.toml
  Cargo.lock
  rust-toolchain.toml

  spec/
    grammar.ebnf
    lexical.md
    semantics.md
    types.md
    effects.md
    memory.md
    contracts.md
    modules.md
    runtime-abi.md
    compatibility.md

  crates/
    gpp-cli/
    gpp-syntax/
    gpp-resolve/
    gpp-types/
    gpp-effects/
    gpp-hir/
    gpp-core/
    gpp-mir/
    gpp-interpreter/
    gpp-codegen-llvm/
    gpp-runtime/
    gpp-package/
    gpp-diagnostics/
    gpp-agent/
    gpp-lsp/
    gpp-verify/

  stdlib/
    core/
    collections/
    text/
    json/
    io/
    fs/
    net/
    test/

  schemas/
    source-ast.schema.json
    agent-protocol.schema.json
    diagnostics.schema.json
    package-interface.schema.json

  tests/
    parse-pass/
    parse-fail/
    check-pass/
    check-fail/
    run-pass/
    run-fault/
    gc-stress/
    ffi/
    sandbox/
    incremental/
    reproducible-builds/
    protocol/

  examples/
    hello/
    json-transform/
    restricted-http-service/
    maintenance-demo/

  bench/
    harness/
    public-development/
    task-schemas/
    baselines/
    manifests/
    analysis/

  docs/
    guide/
    adr/
    ai-language-card.md
    release-checklists/

  tools/
    grammar-export/
    fixture-generator/
    corpus-validator/
    differential-runner/
```

This is an intended boundary map. Do not create dozens of empty crates before the vertical slice exists; begin with a small workspace and split at real dependency boundaries. Sealed qualification tests must not be present in the model-visible checkout.

### 21.2 Workstream ownership

| Workstream | Main ownership | Important boundary |
|---|---|---|
| Language/frontend | Grammar, semantics, checking, formatting | No backend-specific semantics |
| Compiler/runtime | IR, lowering, GC, ABI, platform support | No unverified optimizer assumptions |
| Developer/agent tooling | Diagnostics, context, patches, LSP | No bypass of compiler or authorization |
| Library/packages | APIs, codecs, interop, lockfiles | No implicit authority or install-time code |
| Evaluation | Tasks, models, oracles, metrics, analysis | Separate from tuning against the holdout |
| Security/release | Isolation, provenance, reproducibility, incident handling | Reject unsupported guarantees |

### 21.3 Continuous integration

Every change runs formatter and host-language checks, relevant semantic tests, snapshot/schema tests, and affected examples. Scheduled/release pipelines run fuzz campaigns, differential execution, GC stress, target matrices, sandbox-negative tests, reproducibility, and performance regressions.

Compiler, runtime, and protocol bugs receive minimized regression tests. Documentation examples are extracted and executed once their feature phase exists. An example claiming a future feature is explicitly labeled until then.

---

## 22. Prioritized implementation backlog

| ID | Priority | Deliverable | Acceptance criterion |
|---|---|---|---|
| GPP-001 | P0 | Semantic decisions and ADRs | Arithmetic, ordering, errors, effects, memory, modules are unambiguous |
| GPP-002 | P0 | Independent task/oracle harness | Equivalent tasks run against at least two baseline languages |
| GPP-003 | P0 | Lexer and parser | Positive/negative fixtures and useful truncated-input diagnostics |
| GPP-004 | P0 | Stable formatter | Idempotent output and parse/format/parse equivalence |
| GPP-005 | P0 | Symbol resolution | Undefined/duplicate/ambiguous symbols rejected deterministically |
| GPP-006 | P0 | Scalar type checker | Every operator/call/return rule has positive and negative tests |
| GPP-007 | P0 | Scalar interpreter | Specified results and faults match hand-derived expectations |
| GPP-008 | P0 | Scalar Core/MIR and verifier | Invalid CFG/value/type references rejected before code generation |
| GPP-009 | P0 | LLVM object/native slice | A compiled program runs without the interpreter and model |
| GPP-010 | P1 | Aggregate types and generics | Recursive layout and specialization limits enforced |
| GPP-011 | P1 | Managed heap and roots | Forced collection at every safepoint preserves live objects |
| GPP-012 | P1 | Effect checker and capabilities | Pure-to-effectful and missing-capability paths fail correctly |
| GPP-013 | P1 | Result/match checking | Exhaustiveness and exact-error propagation tested |
| GPP-014 | P1 | Module/package interfaces | Interface hashes and explicit imports drive correct invalidation |
| GPP-015 | P1 | Diagnostics schema | Stable codes, evidence, locations, root-cause grouping |
| GPP-016 | P1 | Context extraction | Mandatory context included or incompleteness explicitly reported |
| GPP-017 | P1 | Atomic body patches | Stale/invalid patches leave the accepted tree unchanged |
| GPP-018 | P1 | JSON/filesystem vertical app | Correct behavior on malformed data and restricted paths |
| GPP-019 | P1 | Sandboxed test runner | Denial tests pass; unavailable isolation fails closed |
| GPP-020 | P1 | Offline/reproducible build path | Prepared identical environments produce specified reproducible artifacts |
| GPP-021 | P2 | Runtime contracts | Checks are retained in all unproved cases |
| GPP-022 | P2 | Property/differential fuzzing | Failures shrink to durable regression fixtures |
| GPP-023 | P2 | Grammar-decoding adapter | Grammar matches compiler syntax; overhead/dead ends measured |
| GPP-024 | P2 | Model adaptation experiment | Licensed, validated, disjoint data and equal-budget controls |
| GPP-025 | P2 | Bounded verifier | Proved/refuted/unknown/unsupported remain distinct |
| GPP-026 | P2 | Scoped resources and FFI | Cleanup, ABI, rooting, and forbidden callback behavior tested |
| GPP-027 | P2 | Additional native target support | Platform-specific conformance and packaging pass |
| GPP-028 | P2 | Qualification report | Costs, failures, uncertainty, and baseline controls published |
| GPP-029 | P3 | Stable WASI profile | Runtime/host API support and policy tested, not merely emitted Wasm |
| GPP-030 | P3 | Structured concurrency design | Task/effect/cancellation/sharing rules reviewed before implementation |

P0 proves the compiler direction. P1 proves practical authoring. P2 supplies assurance and release evidence. P3 remains extension work.

---

## 23. Team, infrastructure, and cost model

### 23.1 Suggested roles

A practical team needs compiler/runtime expertise, language/type-system design, developer-tooling skills, and evaluation/security ownership. People can cover multiple roles, but the responsibilities cannot disappear. An initial small team can build a narrow prototype; a production cross-platform language and runtime should not be estimated as a short syntax project.

Independent review matters most around memory rooting, FFI, capability enforcement, compiler transformations, and the evaluation oracle. AI assistance can accelerate implementation but does not replace those reviews.

### 23.2 Development infrastructure

Ordinary CPU development machines are sufficient for the compiler and most conformance tests. Use macOS ARM64 and Linux x86-64 runners first, then a Windows runner for the planned Windows profile. Pin tools and store minimized regression cases.

A GPU is optional for local-model evaluation or adaptation; it is not a requirement for compiling or executing GPT++. Hosted inference is another experimental option, with cost/privacy policies recorded. Do not bake a specific model subscription or GPU vendor into the language.

Use disposable isolated runners for generated-code execution. Separate the evaluation controller and its credentials from generated programs. Store benchmark manifests, usage accounting, and result artifacts in access-controlled locations with defined retention.

### 23.3 Budget formulas rather than invented prices

```text
engineering_cost = sum(role_effort * actual_loaded_role_rate)

inference_cost = sum(
    uncached_input_tokens * input_price
  + cached_input_tokens * cached_input_price
  + billed_output_tokens * output_price
  + other_documented_provider_charges
)

local_compute_cost = sum(device_hours * actual_hourly_cost)

project_cost = engineering_cost
             + inference_cost
             + local_compute_cost
             + CI_storage_and_execution
             + independent_review
```

Record the pricing date, provider, currency, cache assumptions, and whether output accounting includes reasoning tokens. Obtain actual quotes when budgeting; this plan does not imply current model/GPU pricing.

Use the development pilot to estimate qualification cost and uncertainty before allocating the full experiment. Limit each run by calls, tokens, wall time, and execution resources so a repair loop cannot exhaust the budget.

---

## 24. Risks and decision gates

| Risk | Why it matters | Mitigation | Decision trigger |
|---|---|---|---|
| Familiarity deficit | New syntax may lose to well-trained languages | Familiar constructs, compact guide, validated data | Rework syntax/adaptation if controlled cost stays worse |
| Benefits are mostly tooling | A new language may add ecosystem cost without enough gain | Enhanced baseline controls and ablations | Reuse tool ideas on existing languages where appropriate |
| Overengineering | Types, GC, proofs, concurrency, and packages can swamp the core | Scalar vertical slice; staged feature gates | Cut/defer features not needed for a measured use case |
| Verbosity | Explicit effects/contracts may cost more than they save | Measure actual workflow tokens and errors | Change mandatory metadata policy through an ADR |
| Unsound effect assumptions | Declared effects can conceal FFI or callback behavior | Transitive checking, typed callbacks, trusted FFI boundary | Block release on an effect-safety hole |
| GC miscompilation | Lost roots can invalidate memory safety | Forced safepoint stress, sanitizers, layout tests | Block managed native release |
| Excessive collection costs | Immutable APIs may produce quadratic copies | Persistent structures, profiling, complexity tests | Redesign representation before claiming practicality |
| Grammar/model mismatch | Constraints may reject good continuations or cause stalls | Differential grammar tests and unconstrained fallback | Disable harmful constraining modes |
| Weak correctness oracle | Benchmarks can reward wrong solutions | Hidden independent tests, properties, reviewed references | Quarantine invalid task families and rerun all conditions |
| Holdout contamination | Synthetic data can leak tasks and algorithms | Provenance, family/repository splits, fresh tasks | Replace compromised qualification material |
| Sandbox overclaim | Native execution may retain ambient authority | Tested OS/runtime boundaries and fail-closed commands | Do not run untrusted code where guarantees are unavailable |
| FFI ecosystem pressure | Native packages can erase language guarantees | Admission policy and isolated deployment profiles | Keep unsafe packages outside the restricted profile |
| Platform divergence | Backend support does not ensure runtime compatibility | Per-target tests and support matrix | Mark target experimental until all gates pass |
| Public naming collision | Working names may conflict with other projects | Check before release; retain project identity separately | Rename tooling/extension without changing semantic goals |
| Performance claim inflation | Cherry-picked examples can mislead | Pre-registered comparisons and uncertainty reporting | Label evidence inconclusive/mixed instead of claiming a win |

### Bounded design questions

Several choices deserve experiments rather than endless discussion. Their defaults are already selected, so implementation can proceed.

| Question | Working default | Evidence needed to change it |
|---|---|---|
| Source or AST generation? | Source fragments in transactional patches | Lower total cost and equal acceptance for AST generation |
| Mandatory function effect spelling? | Explicit `!{...}` | Evidence that another representation preserves clarity/checking at lower workflow cost |
| Numeric local identifiers? | Descriptive names | Repeatable gains across tasks/models without review losses |
| Additional pipeline syntax? | No special pipeline syntax initially | Measurable gain exceeding grammar/library complexity |
| Precise or inferred local annotations? | Inference when unique | Repair/cost evidence favoring a stricter rule |
| Custom tokenizer? | No | Amortized benefit after matched adaptation costs |
| Default advanced verifier? | Optional | Robust coverage and acceptable latency on practical programs |
| Self-hosting? | Defer | Clear engineering/adoption value after stable semantics |

---

## 25. Versioning and governance

Keep separate versions for the source edition, compiler, standard library, runtime ABI, package interface schema, diagnostic schema, and agent protocol. A compiler update must not silently reinterpret a source edition.

Before 1.0, mark breaking changes and provide migration notes. After 1.0, source incompatibilities require an edition boundary or another explicitly documented compatibility mechanism. Formatter changes must be reviewed for churn and source-location effects.

A language-change proposal requires motivating examples, alternatives, formal/operational semantics, grammar impact, AI-authoring cost impact, compiler/runtime impact, security analysis, migration plan, and tests. “An LLM likes it” is not sufficient evidence.

Prefer a permissive open-source implementation and an openly available language specification, subject to contributor agreement and dependency-license review. Choose actual project licenses before accepting external contributions; this document is not a license grant.

Publish a security reporting process, release artifacts with integrity metadata, a target support matrix, and an explicit policy for experimental features. Keep benchmark task generation and evaluation review sufficiently independent from language advocacy to allow an unfavorable result.

---

## 26. Definition of done

### 26.1 Native prototype completion

A developer can write a documented subset of GPT++, receive useful type/effect errors, run it in the reference interpreter, compile it into a native executable, and execute that artifact without an LLM or Python/JavaScript source runtime. The compiler must be real even if the language subset is small.

### 26.2 Practical authoring prototype completion

An AI can obtain a compiler-derived context bundle, propose a symbol-level edit, receive structured diagnostics, repair within a fixed budget, and produce an accepted transaction. The system rejects stale patches, permission expansion, unsupported APIs, and unauthorized acceptance-test changes.

### 26.3 Planned sequential 1.0 completion

| Area | Required evidence |
|---|---|
| Specification | Grammar and semantics cover every stable feature; examples are executable |
| Compiler | Checked source lowers through GPT++ IR to native artifacts; no known critical miscompilation |
| Runtime | Memory/rooting, faults, resources, and ABI behavior pass stress and platform tests |
| Core language | Modules, functions, generics, records/enums, collections, errors, and effects are usable together |
| Library | JSON/filesystem/console/network demonstrations work with explicit capabilities |
| Safety | Restricted profile has tested enforcement and a documented trusted base |
| Tooling | Formatter, diagnostics, context bundles, transactional edits, and basic editor support are stable |
| Packages | Locked dependencies, provenance, offline builds, and compatibility policy work |
| Platforms | Each claimed native target passes its declared conformance and packaging suite |
| Assurance | Unit/property/fuzz/differential tests exist; proof claims stay within supported scope |
| Evaluation | Independent baseline-controlled results and complete cost accounting are available |
| Operations | Installation, debugging, upgrade, incident reporting, and limitations are documented |

Each release identifies the supported profile, the conformance evidence for it and the comparisons performed on specific tasks. Publish the cost in tokens, wall time and extra information alongside acceptance for each workflow.

### 26.4 Claims that must not appear without evidence

Do not claim that GPT++ is universally optimal for LLMs, automatically secure, bug-free because it compiles, faster than all established languages, compatible with every model, or the first project to combine AI and language design. Do not claim that a textual syntax shortens inference based only on character counts.

The project aims to make agents better at writing and maintaining working programs. Each comparative claim names the measured advantage, the task families, models and operating conditions where it was observed, and the accompanying costs.

---

## 27. First implementation brief

This section is the handoff for a developer or coding agent starting the repository.

### Objective

Build the smallest end-to-end GPT++ native compiler slice that establishes the architecture. Do not attempt to implement the whole language in one code-generation pass.

### Initial supported program

```gpp
module demo.main;

fn add(left: I64, right: I64) -> I64 !{} {
    return left + right;
}

pub fn main() -> I64 !{} {
    return add(20, 22);
}
```

This uses a **bootstrap-only entry ABI**: a no-argument `main` returning `I64`. The bootstrap runner reports the value as its result. It is not the final capability-based application entry point from Section 8.3, and no final-language compatibility promise is attached to this temporary profile.

### Supported subset

One module; `I64`, `Bool`, and `Unit`; literals; immutable/mutable local bindings; function calls; `return`; conditionals; simple loops; fixed arithmetic/comparison operators; explicit empty effect sets. Add nonempty effects and capabilities before exposing real host I/O. No heap, strings, JSON, packages, FFI, contracts, custom training, or concurrency in this first slice.

### Required implementation sequence

1. Create the workspace, semantic fixture format, and reproducible toolchain configuration.
2. Implement tokens, source spans, parser, and stable AST printing.
3. Implement symbol resolution, type checking, and return-path checking.
4. Implement the interpreter with exact arithmetic/fault semantics.
5. Implement typed Core/MIR and validate every block/value reference.
6. Emit LLVM IR, verify it, generate an object, and link a native runner.
7. Compare interpreter/native results and fault categories on positive and negative tests.
8. Expose `check`, `run --interpreter`, `build`, and machine-readable diagnostics.

### Acceptance tests

The demonstration returns 42. Undefined names, invalid argument types, wrong return types, duplicate declarations, and non-Boolean conditions are rejected. Arithmetic boundary cases fault consistently in debug and optimized native builds. Division by zero and signed-minimum division overflow never reach an undefined native operation. A loop and a recursive scalar function produce the same result in both engines.

Run generated well-typed scalar programs under bounded interpreter/native differential tests, but also retain independent handwritten tests so a shared frontend error is not hidden by agreement.

### Explicit stop point

Once this slice is correct, freeze its fixtures, document its supported syntax, and run the paired scalar authoring pilot in Section 20. Use the observed failures to choose one semantic family at a time from aggregates, errors, effects/capabilities, managed memory, modules, practical libraries, and agent patches. A clean small compiler is a stronger foundation than a large untested compiler-shaped codebase.

### Project north star

> GPT++ should make the model responsible for intent and algorithmic choices, while the compiler and tooling handle routine structure, bookkeeping, validation, and safe execution boundaries.

The final product is not simply “a language AI can write.” It is a language and engineering system whose AI-authoring advantage can be measured, reproduced, and improved without compromising executable semantics.

---

## 28. Research references

Sources below were checked for this design on 27 October 2026. These are primary research, official specifications, or project-maintained documentation. Research results are scoped to their own experiments and are not evidence of GPT++ performance. Living documentation should be pinned or archived when an implementation decision depends on a specific version.

**[R1] LLVM Project — My First Language Frontend with LLVM.** A reference for owning a frontend and generating LLVM/object code.<br>
https://llvm.org/docs/tutorial/MyFirstLanguageFrontend/index.html

**[R2] LLVM Project — LLVM Language Reference Manual.** Reference for IR semantics, arithmetic preconditions, poison, and undefined behavior.<br>
https://llvm.org/docs/LangRef.html

**[R3] Hugging Face Tokenizers — The tokenization pipeline.** Reference for tokenizer stages and why source character count is not a token-cost measurement.<br>
https://huggingface.co/docs/tokenizers/main/en/pipeline

**[R4] Ugare et al. — SynCode: LLM Generation with Grammar Augmentation (2024).** Research precedent for grammar-constrained generation.<br>
https://arxiv.org/abs/2403.01632

**[R5] Mündler et al. — Type-Constrained Code Generation with Language Models (2025).** Research precedent for constraints beyond syntax.<br>
https://arxiv.org/abs/2504.09246

**[R6] Biagiola et al. — The Alignment Problem in Constrained Code Generation (2026).** Research warning about misalignment and incompleteness in generation constraints.<br>
https://arxiv.org/abs/2606.21619

**[R7] Cassano et al. — Knowledge Transfer from High-Resource to Low-Resource Programming Languages for Code LLMs.** MultiPL-T; preprint first submitted in 2023, with a PLDI 2025 publication listed by Microsoft Research.<br>
https://arxiv.org/abs/2308.09895<br>
https://www.microsoft.com/en-us/research/publication/knowledge-transfer-from-high-resource-to-low-resource-programming-languages-for-code-llms/

**[R8] Raihan, Newman, and Zampieri — A Taxonomy of Programming Languages for Code Generation (2026), version 4, revised 1 October 2026.** Research context for uneven language resources.<br>
https://arxiv.org/abs/2604.00239v4

**[R9] Daan Leijen / Koka project — The Koka Programming Language.** Official language documentation; precedent for typed effects.<br>
https://koka-lang.github.io/koka/doc/book.html

**[R10] Dafny project — Dafny Reference Manual.** Official reference for contracts and verification-oriented language design.<br>
https://dafny.org/latest/DafnyRef/DafnyRef

**[R11] Liu et al. — Is Your Code Generated by ChatGPT Really Correct? Rigorous Evaluation of Large Language Models for Code Generation (2023).** EvalPlus research and project material.<br>
https://arxiv.org/abs/2305.01210<br>
https://evalplus.github.io/

**[R12] Jain et al. — LiveCodeBench: Holistic and Contamination Free Evaluation of Large Language Models for Code.** Official project and ICLR 2025 publication page. The title is the authors' title, not an assurance that every use is uncontaminated.<br>
https://livecodebench.github.io/<br>
https://proceedings.iclr.cc/paper_files/paper/2025/hash/94074dd5a072d28ff75a76dabed43767-Abstract-Conference.html

**[R13] WASI and Wasmtime — Security documentation.** Official references for host-granted capabilities and execution-security boundaries.<br>
https://wasi.dev/security<br>
https://docs.wasmtime.dev/security.html

**[R14] XGrammar project — Official repository.** Candidate grammar/structured-generation infrastructure.<br>
https://github.com/mlc-ai/xgrammar

**[R15] llguidance project — Official repository.** Candidate constrained-generation infrastructure.<br>
https://github.com/guidance-ai/llguidance

**[R16] Microsoft — Language Server Protocol specification, version 3.17.** Existing editor-protocol reference; chosen as a pinned reference, not a claim that it is the newest version.<br>
https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/

**[R17] Liu et al. — ShortCoder: Knowledge-Augmented Syntax Optimization for Token-Efficient Code Generation (2026).** Research showing that existing-language efficiency techniques belong in the comparison set.<br>
https://arxiv.org/abs/2601.09703

**[R18] LLVM Project — Garbage Collection with LLVM.** Official reference for compiler/runtime GC integration.<br>
https://llvm.org/docs/GarbageCollection.html

---

**Document conclusion:** Proceed with a small deterministic native compiler and an independently evaluated authoring protocol. Optimize total accepted-work cost, not novelty or visual compactness. Keep the language general-purpose, the semantics explicit, the execution boundaries enforceable, and the efficiency claims empirical.
