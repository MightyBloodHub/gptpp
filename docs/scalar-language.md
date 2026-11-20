# GPT++ scalar language reference

This page describes the language implemented by the current `gpp` compiler. [Grammar](../spec/grammar.ebnf) · [Example program](../examples/add.gpp) · [Long-form design](design.md)

## Language card

| Construct | Behavior |
|---|---|
| Module and entry | A program starts with one dotted module declaration and exposes `pub fn main() -> I64 !{}`. Function signatures include parameter types, a result type, and the empty effect set `!{}`. |
| Values | `I64` is signed 64-bit. `Bool` has the values `true` and `false`. `Unit` has the value `()`. Equality compares values of the same type. Ordering requires integers. |
| Integer conversion | `flag as I64` converts `false` to 0 and `true` to 1. An `I64` operand keeps its value. A cast binds more tightly than multiplication and less tightly than unary operators. For example, `!flag as I64` converts the negated flag. |
| Integer functions | `min(a, b)` and `max(a, b)` return the smaller and larger signed values. `clamp(x, low, high)` returns the closest value to `x` in the inclusive interval and faults with `InvalidBounds` if `low > high`. Operands are I64 and evaluate once, left to right, before the operation. A module declaration of the same name supplies the full signature and behavior. A local of the same name shadows the callable. |
| Bindings and calls | Parameters and `let` bindings are immutable. Use `var` for mutable locals. Mutable integer bindings support `+=`, `-=`, `*=`, `/=`, and `%=`. A nested block can shadow a name. Functions support forward calls and recursion. |
| Control flow | Use `if`, `else if`, `else`, `while`, and `return`. Conditions require `Bool`. Conditional values have two arms of the same type, and only the chosen arm runs. The checker verifies non-Unit return paths and recognizes literal Boolean conditions. A Unit function may fall through. |
| Evaluation order | Operands and arguments evaluate left to right. `&&` and `\|\|` short-circuit. Discarded expressions still execute. |
| Arithmetic | Integer addition, subtraction, multiplication, and unary negation check for overflow. Division truncates toward zero. Division or remainder by zero faults. The minimum `I64` divided by −1 overflows. The corresponding remainder is zero. |
| Limits | The parser bounds nesting and expression height at 64. The interpreter defaults to one million steps and bounds evaluation nesting at 128. Set the step budget with `--fuel N`. Native programs use the host's resources and should be trusted. |

The compiler supports single-file scalar modules today. The [roadmap](../ROADMAP.md) tracks broader features such as imports, records, collections, recoverable errors, and capabilities.

## Inspect and diagnose

From the repository root after building the compiler, run any of the following.

```sh
target/debug/gpp check --format=json examples/add.gpp
target/debug/gpp ast examples/add.gpp
target/debug/gpp emit-llvm examples/add.gpp
```

Successful checks exit silently with status 0. A failed check exits with status 1. In JSON mode, each diagnostic on stderr contains a schema version, stable code, severity, message, file, and half-open UTF-8 byte offsets. The default text output uses one-based line and column numbers. The AST command prints normalized source. The LLVM command shows IR before optimization.

Arithmetic overflow, division by zero and inverted clamp bounds exit with status 1 and report `fault: IntegerOverflow`, `fault: DivisionByZero` or `fault: InvalidBounds` on stderr. The interpreter reports `fault: ResourceLimit` when it exceeds its execution limits. Successful runs print the full signed result from `main`.

The interpreter evaluates checked source. The native backend lowers the program to typed basic blocks and verifies operands, control-flow targets, and slot initialization. LLVM verifies the emitted IR before and after optimization. Native builds use `-O0` by default and link a small C entry point. The executable runs independently of Cargo, LLVM, Python, and the GPT++ compiler.

The native driver searches `GPP_LLVM_BIN`, `PATH`, and the Apple Silicon and Intel Homebrew LLVM locations. On macOS it uses `SDKROOT` when set and otherwise asks `xcrun` for the SDK.

## Trace a call

```sh
target/debug/gpp trace examples/add.gpp --function add --call main
target/debug/gpp trace examples/add.gpp --function add --call add -4 -9 --fuel 1000
```

`--call` names the function to execute. `--function` names the function whose expressions to observe. They can be the same function or a caller can reach the target multiple times. Supply one argument per parameter in declaration order. The CLI accepts signed decimal integers, `true`, `false` and `'()'` for Unit. The interpreter uses the ordinary fuel and nesting limits.

A `gpp.trace/1` response contains the checked source revision, the entry function and arguments, the target function and its source extent, and either `result` or `fault`. Each selectable expression has the same byte range and text as in `gpp expressions`, with a static `type`, a count of visits (`hits`), and observations from its first three visits. Each observation contains the visible bindings on entry and either the resulting `value` or the propagated `fault`. A skipped branch has zero visits and an empty observation list. Integers and booleans use JSON scalars. Unit is JSON `null`. Consumers must preserve signed 64-bit integer precision when decoding JSON.

For the first command, the expression `left + right` ran once with `{"left":20,"right":22}` and returned `42`. Its half-open UTF-8 range is `73:85`. Use that range and the returned revision with `gpp edit` to preview a change to the expression. Tracing is read-only. A runtime fault is a successful observation reported in the JSON response. An invalid program, unknown function or ill-typed invocation exits with an error.

## Check several candidate edits in one process

`gpp probe FILE --function TARGET --expect REVISION --cases CASES.tsv [--wrapped] [--filter]` opens a read-only session against the exact source bytes identified by the revision. Each proposed replacement uses the same range, grouping and type checks as `gpp edit --at … --expr … --stdout`. Each replacement starts from the original source.

The cases file contains one call per line. Start with the function name and separate its arguments with tabs. A zero-argument call consists of the name alone. Use the scalar literals accepted by `gpp trace`. With `--filter`, append the expected result as the final tab-separated field of each line. The compiler checks all call signatures and labels before opening the session.

For example, this command tries subtraction and multiplication at the addition site in the example module.

```sh
printf 'main\nadd\t4\t3\n' > target/calls.tsv
revision=$(target/debug/gpp revision examples/add.gpp)
printf '73:85 12\nleft - right73:85 12\nleft * right' |
  target/debug/gpp probe examples/add.gpp --function add --expect "$revision" --cases target/calls.tsv
```

The first JSON line contains `schema` (`gpp.probe/1`), `revision` and the number of `cases`. The next two lines report results of `[-2, 1]` and `[440, 12]` in case order.

| Input or mode | Behavior |
|---|---|
| Candidate frame | Send the ASCII header `START:END LENGTH`, a single LF, then exactly `LENGTH` bytes of UTF-8 expression text. Put the next header immediately after the fragment. The header limit is 96 bytes including LF. The fragment limit is 4 MiB. |
| Outcome response | A checked edit produces `{"status":"ok","outcomes":[…]}` with one `{"result":value}` or `{"fault":"FaultName"}` per call. Each call gets its own default fuel budget and call stack. |
| Checked candidates only | Append ` check` before the header's LF to validate the edit and receive an empty outcomes array. |
| `--filter` | A checked edit returns `{"status":"ok","matches":true}` if every call matches its expected scalar. The first mismatch or runtime fault returns `false`. |
| `--wrapped` | Evaluate each call through the authoring tools’ I64 entry wrapper. This preserves the public-example runner’s fuel and nesting behavior, including its conversion of Bool and Unit results. The response exposes the original scalar type. |
| Errors | An invalid span, rejected fragment or type error returns `{"status":"invalid","error":"…"}` and the session accepts the next frame. A stale revision or invalid case prevents startup. A malformed or truncated frame terminates the process with a nonzero exit. |

Each response flushes before the compiler reads the next candidate. Close stdin at a frame boundary to end the session. Later edits to the source file have their own revision. Apply a chosen replacement separately with the original revision guard.

## Preview a function edit

The checked editor accepts a replacement body or a single return expression. It preserves the declaration and source outside the selected function body. This example previews making `add` return the larger argument, then runs the preview.

```sh
printf '%s\n' 'if left > right { left } else { right }' > target/larger.expr
target/debug/gpp edit examples/add.gpp --function add \
  --expr target/larger.expr --stdout > target/preview.gpp
target/debug/gpp run --interpreter target/preview.gpp
```

The preview prints `22`. For in-place application, capture the base with `gpp revision FILE` before drafting and supply that revision with `--expect` when applying. The optional proposal tool can generate such a fragment and validate public examples against the checked preview. [Authoring guide](../tools/README.md)

## Preview an edit inside a function

An editor can ask the compiler which expressions belong to a function. The listing includes the source revision, the function extent and each selectable expression's original text. All ranges are half-open UTF-8 byte offsets from the start of the file. Two occurrences of the same text have different ranges.

```sh
target/debug/gpp expressions examples/add.gpp --function add
```

For the checked-in example, `left + right` occupies bytes `73:85`. The following commands preview changing just that addition to a subtraction. The interpreter prints `-2`.

```sh
base_revision=$(target/debug/gpp revision examples/add.gpp)
printf '%s\n' 'left - right' > target/subtract.expr
target/debug/gpp edit examples/add.gpp --function add --at 73:85 \
  --expr target/subtract.expr --expect "$base_revision" --stdout > target/subtract-preview.gpp
target/debug/gpp run --interpreter target/subtract-preview.gpp
```

Use the range and revision from the same listing when integrating an editor. The compiler validates the fragment as one expression, adds grouping when needed, and checks the resulting module. An in-place edit requires `--expect`. The proposal tool can also select an expression from the original function text and check the result against caller examples. [Model-assisted expression edits](../tools/README.md#edit-an-expression-inside-the-target)
