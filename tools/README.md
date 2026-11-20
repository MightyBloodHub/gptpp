# Draft a GPT++ function change

Use a local Ollama model to draft a replacement for one function in a checked scalar module. The tool shows a diff and saves a fragment against the SHA-256 revision it inspected. Applying the edit is a separate command.

Build the compiler, start your local Ollama service and choose an installed model from `ollama list`. The following example uses the repository's two-argument `add` function.

```sh
cargo build --locked --offline
python3 tools/propose.py examples/add.gpp --function add \
  --task 'Return the larger of left and right.' \
  --model deepseek-coder:6.7b --expr -o target/larger.expr
```

Use `--expr` for one return expression, `--body` for a list of statements, or `--maintenance` for the experimental native editing preset below. The output path must be new. The tool reads the target declaration and current body from the compiler's normalized AST. Ordinary native GPT++ generation also supplies the other function signatures in the module. It checks that the selected model is installed locally before sending this context to the loopback Ollama service. A rejected completion can receive one retry with a diagnostic. Whole-body and return-expression proposals use the compiler's normalized GPT++ spelling. A selected-expression edit saves the checked insertion for that range. The preview reflects the exact fragment saved to disk.

Read the diff and the saved fragment. The terminal displays the base revision and the exact `gpp edit` command to apply the proposal. To verify behavior before applying, use the printed revision with a preview and the interpreter. For this example `main` calls the changed function with 20 and 22, so the expected result is 22.

```sh
target/debug/gpp edit examples/add.gpp --function add --expr target/larger.expr \
  --expect 'sha256:<copy the printed digest>' --stdout > target/larger-preview.gpp
target/debug/gpp run --interpreter target/larger-preview.gpp
```

Compiler validation covers parsing, types and checked IR. Run your behavioral tests against the proposed module. An edit using an outdated base revision fails if the source changed during generation or after review.

## Repair an expression against source contracts

The offline contract repair tool takes a module with finite contracts and a target function. It searches for a single-expression edit and checks candidates against the module’s contracts. A failing input comes from executing the source predicate. An agent can use it even when nobody has supplied a list of expected return values.

The queue example has eight slots. Start by preparing the full-queue preview in the [finite contract walkthrough](../docs/scalar-language.md#verify-a-finite-contract), then run the repair tool on that preview.

```sh
python3 tools/contract_repair.py target/full-queue.gpp --function can_admit
```

For the published queue example, the search replaces the occurrence of `queued` inside the faulty test with `queued + 1`. The resulting comparison `(queued + 1) <= 8` passes all nine inputs. Search stops at the first candidate that passes every input of every source contract. To save that replacement to a new file, add `-o target/queue-repair.expr`. The `gpp.contract-repair/1` response supplies the target range, source revision and guarded apply arguments. Applying the saved fragment uses `gpp edit --expect … --verify --budget …` to recheck the complete edited module before installing it. The source remains available for review.

Set `--edits N` to bound the number of candidates and `--budget N` to bound the assignments in each candidate verification. With `--menu FILE`, pass an existing `gpp.repair/1` menu for the same target and revision. The tool checks the supplied entries. Multiple fully verified entries produce an ambiguous result because different expressions may agree on the entire declared domain. Incomplete checks and unsuccessful searches do not publish a replacement.

An agent can inspect the original counterexample in the target function, including through helper calls.

```sh
target/debug/gpp trace target/full-queue.gpp --function can_admit --contract respects_capacity 8
```

The contract covers nine queue sizes. Review the chosen predicate and bounds before relying on the edit for other inputs.

### Ask a local model to edit from the source contract

With a local Ollama server and a pinned model installed, the experimental agent editor can use the contracts already in the module as the task specification.

```sh
python3 tools/agent_edit.py target/full-queue.gpp --function can_admit \
  --contracts --model qwen2.5-coder:7b -o target/agent-queue.expr
```

The model receives the source contracts and the first counterexample. It can propose a single expression, then revise it once after a failed check. A proposal must pass every selected input of every source contract. The saved fragment’s guarded apply command repeats that verification on the exact edit. In a six-assignment development study, Qwen2.5-Coder 7B repaired the capacity task on its first attempt and completed one of three tasks. StarCoder2 3B completed none of the three. [Model outcomes and cost](../bench/contracts/model-results.md)

## Search for an edit with public examples

`repair.py` accepts the same cases file as the other authoring tools. Give it the target function and any checked examples, including calls to other functions in the module. The [quick start](../README.md#find-an-edit-from-examples) creates `target/difference.json`. Save an offline menu or let a local model choose from it.

```sh
python3 tools/repair.py examples/add.gpp --function add \
  --cases target/difference.json --list > target/difference-menu.json
python3 tools/repair.py examples/add.gpp --function add \
  --task 'Return left minus right for every pair.' --cases target/difference.json \
  --model qwen2.5-coder:7b -o target/difference.expr
```

Each example runs through the reference interpreter. The search considers integer and Boolean sites reached on **every** failing example, including visits reached through callers. It orders sites by how many passing examples visited them, then tries one replacement per site per round. It tries local names, small constants, neighboring operators, integer increments and decrements (optionally gated by a Boolean), and arithmetic and comparisons among visible locals. The grammar generates single-expression edits and uses no language model. The search streams candidates to one compiler process. For each checked preview it tests the original failures first, then the remaining examples. A mismatch or fault eliminates the candidate immediately. All calls use the public-example runner’s entry-wrapper semantics. The defaults limit the search to 512 tested edits and a menu of 12 passing candidates. `--budget N` changes the work limit.

The `gpp.repair/1` JSON includes the original observations, revision, list of edits, number tested and `stop_reason`. Each edit contains the exact old text, source byte range and replacement. `--list` returns `listed`, `already_passes` or `no_candidates`. A one-based selection from a model returns `selected`, writes a new fragment file and gives an `apply` argument array for the checked editor. A model can return zero and the tool reports `abstained`. For an agent integration, inspect the selected edit and pass the argument array directly to a subprocess when ready to apply it. Every candidate in the menu passed the supplied examples. Withheld tests can still reject it. [Development comparison](../bench/expression/results/repair.md)

### Ask for an example that distinguishes candidate edits

A single example can describe several different programs. Suppose the only known requirement is that `add(3, 3)` should return zero. The search finds nine edits that satisfy it. Give the following command a small pool of valid, **unlabeled** calls. It streams the menu to one compiler process bound to the source revision. Each selected candidate runs directly on the supplied calls, with a fresh interpreter budget for each. [Compiler probe protocol](../docs/scalar-language.md#check-several-candidate-edits-in-one-process)

```sh
printf '%s\n' '[{"args":[3,3],"expected":0}]' > target/one-example.json
printf '%s\n' '[{"args":[2,5]},{"args":[0,3]},{"function":"main","args":[]}]' > target/probes.json
python3 tools/repair.py examples/add.gpp --function add \
  --cases target/one-example.json --list > target/menu.json
python3 tools/distinguish.py examples/add.gpp --menu target/menu.json --probes target/probes.json
```

The tool asks what `add(2, 5)` should return. That input separates 26 of the 36 candidate pairs. An expected result of `-3` selects only candidate 1, `left - right`. An expected result of `3` selects only candidate 5, `right - left`. Obtain the answer from someone who knows the requirement or from an independent implementation. If no predicted outcome matches, the current menu cannot satisfy the answer.

In the `gpp.distinguish/1` response, `question.outcomes` groups original one-based candidate IDs by observed result or fault. When several IDs match the answer, pass them to `--candidates` as a comma-separated list and ask again. Tie scores keep the first probe. A status of `indistinguishable` means no supplied call separates the remaining IDs. Larger domains can contain other distinguishing inputs.

## Experimental native maintenance preset

Use `--maintenance --cases FILE` for a compact full-body edit. The first request shows the task, up to three public assertions in file order, the current target body, a GPT++ syntax reminder and the declaration. Every supplied assertion runs after the compiler accepts the edit. A failed example in a direct or transitive caller triggers one retry with the previous completion, the mismatch or runtime fault, and bounded excerpts of the checked callers. A failed target assertion, unrelated assertion or compiler check ends the run. Pass `--attempts 1` for a single call.

This example changes `add` to return the larger argument and tests both the existing caller and the target. Start local Ollama and install the preset's default model with `ollama pull qwen2.5-coder:7b` if needed.

```sh
cargo build --locked --offline
cat > target/maintenance-cases.json <<'JSON'
[
  {"function": "main", "args": [], "expected": 22},
  {"args": [-4, -9], "expected": -4},
  {"args": [3, 3], "expected": 3}
]
JSON
python3 tools/propose.py examples/add.gpp --function add \
  --task 'Return the larger of left and right.' --maintenance \
  --cases target/maintenance-cases.json -o target/larger.body
```

Add `--prepend` to propose statements above the existing body. The original normalized statements appear in the protected infill suffix and in the checked fragment. Early returns can handle new cases while continuing to the old body for the rest. Either edit form accepts `--caller-obligation PROGRAM` to present an exact target result on the retry when the caller analysis succeeds. [Caller obligation analyzer](caller_obligation.md)

The preset uses a 2,048-token context, a limit of 240 generated tokens, seed 42 and greedy decoding. A retry uses seed 43 and temperature 0.25. Each request preserves the model's stop strings and adds a flush-left function closer. Models with a native `.Suffix` template receive separate prefix and suffix fields. The StarCoder2 3B digest measured in v7 also supports its raw prefix/suffix/middle transport and control-token stops. Choose it with `--model starcoder2:3b`. Other artifacts require a suffix-capable template.

The command uses the v7 native full-body and prepend prompt layouts and sampling settings. The CLI normalizes the body through the compiler, exposes up to three supplied cases, verifies that a named function actually calls the target before retrying, and validates all supplied cases before publishing the fragment. The benchmark used three public cases per task and a separate withheld set. These settings are experimental. [v7 protocol](../bench/policy/protocol.md)

### Edit an expression inside the target

Add `--locate` to let the model select the expression. Its first call receives the change request, public examples and the exact source of the target function. The model copies an existing expression on one line. The tool resolves the text against the compiler's expression catalog for that revision. An absent or ambiguous selection ends the run. The compiler checks each proposed replacement and the CLI runs every supplied case.

The default `--locate separate` takes a second call to fill the selected gap. Use `--locate combined` to request the old and new expressions together. The model completes a two-line change with a prefilled `-` before the old expression and a generated `+` before its replacement. The table counts generation calls when the selection succeeds. A caller-triggered retry fills the same gap in either mode.

| Expression selection | Calls with `--attempts 1` | Maximum calls with caller retry |
| --- | ---: | ---: |
| `--locate` or `--locate separate` | 2 | 3 |
| `--locate combined` | 1 | 2 |
| `--at START:END --expect REV` | 1 | 2 |

This command uses the `target/maintenance-cases.json` file from the preceding example.

```sh
python3 tools/propose.py examples/add.gpp --function add --maintenance --locate combined \
  --task 'Return the larger of left and right.' --attempts 1 \
  --cases target/maintenance-cases.json -o target/located.expr
```

To supply the exact location yourself, obtain the global UTF-8 byte range and revision from one compiler listing. In the checked-in example `left + right` occupies the half-open range `73:85`. When you use a different file or revision, read its range from its own listing.

```sh
target/debug/gpp expressions examples/add.gpp --function add > target/add-expressions.json
selection_revision=$(python3 -c 'import json; print(json.load(open("target/add-expressions.json"))["revision"])')
python3 tools/propose.py examples/add.gpp --function add --maintenance --at 73:85 \
  --expect "$selection_revision" --task 'Return the larger of left and right.' \
  --attempts 1 --cases target/maintenance-cases.json -o target/selected.expr
```

All three forms save the replacement expression and print a revision-guarded command to apply it. The compiler preserves source bytes outside the selected range and groups the replacement when needed to preserve how the surrounding expression parses.

The benchmark includes an offline replay for these three CLI paths. It serves archived model responses over loopback, runs the real proposal command, compares its outgoing requests and selected ranges, and applies each published fragment in a temporary directory. It checks the patch hash and reruns the withheld cases. The replay reports any retry whose caller excerpts differ because the CLI displays the compiler's normalized source. Run it from the repository root with the benchmark Python environment and matching compiler build.

```sh
target/empirical-venv/bin/python -B bench/expression/replay_product.py bench/expression/results/expression.jsonl
```

### Pick a numbered expression

The experimental catalog tool gives each selectable expression its own ID and line number. The local model returns an ID and replacement in one schema-constrained JSON response. This lets it distinguish repeated occurrences of the same expression. Every generated ID maps to a concrete span on the original source revision. The compiler checks the edited module and the tool runs every supplied case before saving the expression.

```sh
python3 tools/indexed_edit.py examples/add.gpp --function add \
  --task 'Return the larger of left and right.' --cases target/maintenance-cases.json \
  -o target/indexed.expr
```

This workflow makes one model call. The full expression list consumes prompt tokens, and a valid ID can still identify the wrong site. The benchmark measures the cost of that list and the number of edits that pass withheld tests. [Catalog study](../bench/expression/README.md)

## Check a proposal against examples

Pass `--cases FILE` to require the proposed function to satisfy a nonempty JSON list of examples. Each `args` list follows the parameter order in the function declaration. Use signed 64-bit JSON integers for `I64`, JSON booleans for `Bool`, and JSON `null` for `Unit`. The same rules apply to `expected`.

A case may include a `function` field naming another checked function in the module. Its own signature determines the argument and result types. This lets a leaf edit satisfy assertions about its callers. For example, `{"function":"main","args":[],"expected":22}` checks the existing entry after the proposed edit. Cases without this field call the edited function.

For the change to `add` above, save the following as `target/larger-cases.json` and add `--cases target/larger-cases.json` to the proposal command.

```json
[
  {"args": [20, 22], "expected": 22},
  {"args": [-4, -9], "expected": -4},
  {"args": [3, 3], "expected": 3}
]
```

The tool validates the examples before generation and includes the first three in the prompt. It evaluates the exact checked proposal in a scratch module using one million interpreter steps per example. If a case fails, the retry receives the named arguments and the observed result or fault. The tool saves a proposal only after every case passes. The reviewed source keeps its original entry function.

## Read caller context for a leaf edit

Add `--caller-context` to show the model how other functions use the selected function's result. The tool follows direct calls in the checked module's AST dump and includes up to three callers within two call steps. Direct callers come first, with name order breaking ties. Each entry includes its signature, the function it calls, and up to three source lines around the earliest relevant call. Long signatures and lines are clipped. Cycles contribute each caller once. A Python-syntax proposal sees the actual GPT++ callers.

The caller excerpts provide read-only context. The proposal, preview and application command continue to target only the function selected by `--function`. Combine `--caller-context` with `--cases` to exercise the caller-visible behavior before saving.

Use `--caller-context-on-failure` to start with the target's declaration, body, task and supplied examples. This mode omits other function signatures and caller excerpts from the first prompt. If the first failing example names a function that directly or transitively calls the target, a wrong result or runtime fault adds the bounded caller excerpts to the single retry. Failures in the target itself, unrelated functions, parsing or checking keep the retry focused on the target. Cases run in file order, so their order determines which failure reaches the retry. Choose one caller-context mode per invocation.

The default `--attempts 2` permits one retry after a validation failure. Choose `--attempts 1` for one proposal. Choose `--attempts caller --cases FILE` to spend a second call only when the first failing example names a direct or transitive caller of the target. This setting enables caller context on that retry and ends immediately on a failed check, target example or unrelated example.

## Native infill and Python-syntax fragments

Use `--infill` with a locally installed infill model, such as `qwen2.5-coder:7b`. The tool checks the installed template for `.Suffix` support, then sends the source prefix and protected suffix to Ollama. The model fills the gap inside the existing declaration. The default generation surface is GPT++.

Add `--stop-at-boundary` to request model-side stopping during infill. On the GPT++ surface the additional stop is a newline followed by a flush-left `}`. On the Python surface the stops are newlines followed by `def `, `class `, `import `, `from `, `assert `, `print(`, `if __name__` or `@`. The tool preserves the model's explicit default stop strings, removes duplicates, and sends the combined list on each attempt. The compiler and any supplied cases still validate the returned fragment, including output that ends early.

```sh
python3 tools/propose.py examples/add.gpp --function add \
  --task 'Return the larger of left and right.' --model qwen2.5-coder:7b \
  --infill --expr -o target/larger-infill.expr
```

Add `--surface python` to infill an expression or body in restricted Python syntax. The prompt includes the actual GPT++ starter and a Python declaration derived from its checked parameter and result types. This surface supports `I64` and `Bool`. It parses the proposed fragment, lowers it to GPT++ and runs the same compiler checks. Arithmetic uses GPT++ semantics, including checked overflow and integer division toward zero. Published fragments in both modes are GPT++ and use the same revision-guarded application command.

The proposal tool supports the integer calls `abs(x)`, `min(a, b)` and `max(a, b)` on this surface. Each requires its positional integer operands. A parameter or local binding with the same name prevents that builtin call in the fragment. The tool expands these operations into checked scalar comparisons and conditionals. Operands are pure and evaluate left to right in the comparison. The selected operand can be evaluated again, which can increase interpreter fuel use. An unselected outer branch remains lazy. Taking the absolute value of the smallest `I64` produces `IntegerOverflow`. Fragments that use these builtins have a limit of 1,024 AST nodes after expansion. Binding a nested calculation to a local before reusing it reduces expansion.

```sh
python3 tools/propose.py examples/add.gpp --function add \
  --task 'Return the larger of left and right.' --model qwen2.5-coder:7b \
  --infill --surface python --expr -o target/larger-projected.expr
```

## Propose ordered exceptions

Use `--surface policy --body --infill` for a change that adds exceptions to an existing scalar function. The model receives the checked signature and current implementation. It fills the gap between a protected `when ` prefix and a protected final `else => @keep` line. Each inserted guard must return a boolean. Its result must match the function's `I64` or `Bool` return type. The first matching rule returns immediately. If every guard fails, the checked original body runs.

For example, this proposal asks for one exception to `add`. The unchanged entry still returns 42 through the fallback.

```sh
python3 tools/propose.py examples/add.gpp --function add \
  --task 'When left is negative, return right. Preserve every other result.' \
  --model qwen2.5-coder:7b --infill --surface policy --body \
  --attempts 1 -o target/add-exception.body
```

Policy infill always requests model-side stops at a newline followed by `else` or `#`, and at a triple-backtick fence. The full returned text must still parse between the protected boundaries. Omit `--infill` to request a complete ordered policy from a chat model, including its explicit final value or `@keep`. Both forms lower the result to a GPT++ body, run the compiler and any supplied `--cases`, and print the revision-guarded application command. [Policy syntax and standalone preview](policy.md)

## Offline verification

```sh
cargo build --locked --offline
python3 -B tools/test_propose.py
python3 -B tools/test_caller_context.py
python3 -B tools/test_scalar_builtins.py
python3 -B tools/test_policy_ir.py
```

These tests exercise the CLI with a deterministic loopback HTTP stub and the real compiler. They cover chat and infill request formats, translation of Python expressions and bodies, checked division semantics, scope boundaries, preview, explicit application, retries, stale revisions and output races.

### Derive a target result from a failed caller

Build the optional caller analyzer and pass its path with `--caller-obligation target/caller-obligation --cases cases.json`. The first prompt uses the target and public examples. A failing caller test can trigger one retry. For example, if the unchanged caller returns `30 - 2 * discount(4)` and its public test expects 26, the retry can ask for `discount(4) = 2`. The analyzer checks this result against the caller’s integer operations. If the caller branches on that unknown result or combines different target inputs, the retry receives the bounded caller excerpts. [Build instructions, supported operations and limits](caller_obligation.md)

### Generate an expression after an empty search

When bounded repair search runs out of candidates, `agent_edit.py` can generate a new expression at a compiler-listed site. The model receives the requested behavior, caller excerpts, and what the starter returned on the supplied examples. A compiler error or failing example allows one retry on the original source. The tool checks every supplied case before saving a fragment. The JSON result includes the attempt outcomes, usage, and a revision-guarded `apply` argument list for a passing proposal. Add `--transcript` to include model prompts and responses.

For example, convert the sample addition to subtraction. The visible checks exercise a direct call and its existing caller.

```sh
cargo build --locked --offline
cat > target/subtraction-cases.json <<'JSON'
[{"args":[8,3],"expected":5},{"function":"main","args":[],"expected":-2}]
JSON
python3 tools/agent_edit.py examples/add.gpp --function add \
  --task 'Return left minus right.' --cases target/subtraction-cases.json \
  --model qwen2.5-coder:7b -o target/subtraction.expr
```

A `proposed` status means the fragment passed those examples. A `rejected` status records both failed attempts and leaves no fragment. [Matched generation protocol](../bench/expression/agent-protocol.md)

GPT++ expressions may use an explicit `as I64` conversion and native `min`, `max` and `clamp` integer operations. In a retrospective on the three arithmetic tasks, the compiler accepted previously generated Qwen expressions using those spellings. The saved model prompts and responses were unchanged. [Replay results](../bench/expression/results/compat.md)
