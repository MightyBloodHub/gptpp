# GPT++ scalar language reference

This page describes the language implemented by the current `gpp` compiler. [Grammar](../spec/grammar.ebnf) · [Example program](../examples/add.gpp) · [Long-form design](design.md)

## Language card

| Construct | Behavior |
|---|---|
| Module and entry | A program starts with one dotted module declaration and exposes `pub fn main() -> I64 !{}`. Function signatures include parameter types, a result type, and the empty effect set `!{}`. |
| Values | `I64` is signed 64-bit. `Bool` has the values `true` and `false`. `Unit` has the value `()`. Equality compares values of the same type. Ordering requires integers. |
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

An arithmetic fault exits with status 1 and reports `fault: IntegerOverflow` or `fault: DivisionByZero` on stderr. The interpreter reports `fault: ResourceLimit` when it exceeds its execution limits. Successful runs print the full signed result from `main`.

The interpreter evaluates checked source. The native backend lowers the program to typed basic blocks and verifies operands, control-flow targets, and slot initialization. LLVM verifies the emitted IR before and after optimization. Native builds use `-O0` by default and link a small C entry point. The executable runs independently of Cargo, LLVM, Python, and the GPT++ compiler.

The native driver searches `GPP_LLVM_BIN`, `PATH`, and the Apple Silicon and Intel Homebrew LLVM locations. On macOS it uses `SDKROOT` when set and otherwise asks `xcrun` for the SDK.

## Preview a function edit

The checked editor accepts a replacement body or a single return expression. It preserves the declaration and source outside the selected function body. This example previews making `add` return the larger argument, then runs the preview.

```sh
printf '%s\n' 'if left > right { left } else { right }' > target/larger.expr
target/debug/gpp edit examples/add.gpp --function add \
  --expr target/larger.expr --stdout > target/preview.gpp
target/debug/gpp run --interpreter target/preview.gpp
```

The preview prints `22`. For in-place application, capture the base with `gpp revision FILE` before drafting and supply that revision with `--expect` when applying. The optional proposal tool can generate such a fragment and validate public examples against the checked preview. [Authoring guide](../tools/README.md)
