# Draft a GPT++ function change

Use a local Ollama model to draft a replacement for one function in a checked scalar module. The tool shows a diff and saves a fragment against the SHA-256 revision it inspected. Applying the edit is a separate command.

Build the compiler, start your local Ollama service and choose an installed model from `ollama list`. The following example uses the repository's two-argument `add` function.

```sh
cargo build --locked --offline
python3 tools/propose.py examples/add.gpp --function add \
  --task 'Return the larger of left and right.' \
  --model deepseek-coder:6.7b --expr -o target/larger.expr
```

Use `--expr` for one return expression, `--body` for a list of statements, or `--maintenance` for the experimental native editing preset below. The output path must be new. The tool reads the target declaration and current body from the compiler's normalized AST. Ordinary native GPT++ generation also supplies the other function signatures in the module. It checks that the selected model is installed locally before sending this context to the loopback Ollama service. A rejected completion can receive one retry with a diagnostic. Successful proposals use the compiler's normalized GPT++ spelling. The preview reflects the exact fragment saved to disk.

Read the diff and the saved fragment. The terminal displays the base revision and the exact `gpp edit` command to apply the proposal. To verify behavior before applying, use the printed revision with a preview and the interpreter. For this example `main` calls the changed function with 20 and 22, so the expected result is 22.

```sh
target/debug/gpp edit examples/add.gpp --function add --expr target/larger.expr \
  --expect 'sha256:<copy the printed digest>' --stdout > target/larger-preview.gpp
target/debug/gpp run --interpreter target/larger-preview.gpp
```

Compiler validation covers parsing, types and checked IR. Run your behavioral tests against the proposed module. An edit using an outdated base revision fails if the source changed during generation or after review.

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
