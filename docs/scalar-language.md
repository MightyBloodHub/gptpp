# GPT++ scalar language reference

This page describes the scalar and structured-value profile implemented by the current `gpp` compiler. [Grammar](../spec/grammar.ebnf) · [Example program](../examples/add.gpp) · [Long-form design](design.md)

## Complete a state transition

GPT++ supports named records, enums and typed expression holes. The reservation component uses a record to return the new seat count, the booking state and an explicit outcome. Records are flat and may contain scalar values or enum tags. Constructors take fields in declaration order. A record can be returned, passed to another function, projected with `.` or compared for equality with another value of the same named type. Enum tags use `Type::Variant`. [Complete application and both host clients](../examples/reservations/README.md)

A function can leave an expression such as `?repeat: Outcome` unfinished. The compiler checks the surrounding function and reports which locals are in scope. Ordinary execution and native builds require a complete module. From the repository root, the following commands create the reservation sketch, inspect its hole and write a verified completion to a new file.

```sh
cargo build --locked --offline
python3 examples/reservations/check.py --sketch > target/booking-sketch.gpp
target/debug/gpp holes target/booking-sketch.gpp
target/debug/gpp complete target/booking-sketch.gpp --hole repeat
target/debug/gpp complete target/booking-sketch.gpp --hole repeat --stdout > target/completed-booking.gpp
target/debug/gpp verify target/completed-booking.gpp
```

Use the hole name from the inspector. The compiler builds typed expressions from lexical variables, record fields, enum tags, visible operations, local helper calls and expressions already present in the target function. It combines terms in increasing stages and uses counterexamples from earlier attempts to reject later candidates. Supply `--fill expression.txt` to check a single model-proposed expression. The command accepts one hole per module. `--expect` can pin the input revision.

By default, `--search hybrid` also consults public contracts if its initial grammar candidates produce no passing program. For integer and Boolean holes it runs sampled contracts with trial values at the hole, remembering the surrounding locals and previously inferred results. It groups expressions by the values they produce on these examples, tries integer coefficients and joins expressions that satisfy opposite branches of a condition. Inferred examples guide the search. Each proposed completion still undergoes whole-module type checking and finite contract verification. `--search grammar` turns off the example-guided stage for comparison.

The default limit is 256 complete candidate expressions and 10,000 assignments per full verification. The guided stage can begin halfway through the candidate allowance or when the initial grammar runs out. It needs at least eight candidate slots. It samples up to 32 public assignments, uses up to 768 additional contract runs (also capped by `--budget`), and considers up to 24,000 intermediate value vectors. It can submit up to 16 additional expressions within the same total candidate limit. The JSON `guidance` fields report contract runs, inferred examples, value vectors, branch combinations and proposals. These extra computations affect elapsed time.

When passing expressions disagree on a direct probe, the compiler returns two expressions, a concrete input and their observed outcomes. The `first_passing` field identifies the first expression that passed the public contracts in this ambiguous search. The finite probes can miss differences. A verified selection is the first passing candidate in search order when no inspected pair showed a disagreement. The JSON reports the checked domain, candidate count, truncation flag and probe count. An ambiguous or incomplete search exits with status 3. A rejected expression exits with status 1. With `--stdout`, a verified command emits a complete module and failures leave stdout empty.

## Prove a contract across a full integer range

`gpp prove` translates checked expressions to Z3 bit vectors and nominal datatypes and asks whether the contract can return false or raise a semantic fault. Install Z3 on the command search path to use this optional command. Its supported fragment includes checked signed arithmetic, branches, immutable locals, records, enums and acyclic function calls. It models short-circuit evaluation, signed overflow, truncating division, signed remainder and faults in discarded eager arguments. It reports unsupported loops, writes or recursion explicitly. A proof covers the declared input range under the source semantics. Native ABI, host storage and interpreter resource limits have separate tests.

```sh
cat examples/reservations/booking.gpp examples/reservations/cancellation.proof.gpp.inc > target/booking-proofs.gpp
target/debug/gpp prove target/booking-proofs.gpp --contract active_cancel_twice
target/debug/gpp prove target/booking-proofs.gpp
```

The full-width cancellation property calls the production transition twice and compares its complete record with the expected count, state and outcome. An active booking owns one seat, so the initial number of available seats can range from zero through `I64::MAX - 1`. For an already cancelled or unseen booking, the properties also cover `I64::MAX`. A satisfiable solver result is reported as refuted only after the reference interpreter reproduces the failure on its model. Solver timeouts, unavailable models or unavailable Z3 yield `unknown`. `--timeout-ms N` sets the solver timeout per query. The solver and its translation are trusted for the `proved` outcome. [Executable proof obligations](../examples/reservations/cancellation.proof.gpp.inc)

## Language card

| Construct | Behavior |
|---|---|
| Module and entry | A program starts with one dotted module declaration and exposes `pub fn main() -> I64 !{}`. Function signatures include parameter types, a result type, and the empty effect set `!{}`. |
| Values | `I64` is signed 64-bit. `Bool` has the values `true` and `false`. `Unit` has the value `()`. Equality compares values of the same type. Ordering requires integers. |
| Integer conversion | `flag as I64` converts `false` to 0 and `true` to 1. An `I64` operand keeps its value. A cast binds more tightly than multiplication and less tightly than unary operators. For example, `!flag as I64` converts the negated flag. |
| Integer functions | `min(a, b)` and `max(a, b)` return the smaller and larger signed values. `clamp(x, low, high)` returns the closest value to `x` in the inclusive interval and faults with `InvalidBounds` if `low > high`. Operands are I64 and evaluate once, left to right, before the operation. A module declaration of the same name supplies the full signature and behavior. A local of the same name shadows the callable. |
| Finite contracts | A named Boolean predicate can be checked over a declared combination of integer ranges and Boolean inputs. The verifier reports a result for the supplied source revision. |
| Bindings and calls | Parameters and `let` bindings are immutable. Use `var` for mutable locals. Mutable integer bindings support `+=`, `-=`, `*=`, `/=`, and `%=`. A nested block can shadow a name. Functions support forward calls and recursion. |
| Control flow | Use `if`, `else if`, `else`, `while`, and `return`. Conditions require `Bool`. Conditional values have two arms of the same type, and only the chosen arm runs. The checker verifies non-Unit return paths and recognizes literal Boolean conditions. A Unit function may fall through. |
| Evaluation order | Operands and arguments evaluate left to right. `&&` and `\|\|` short-circuit. Discarded expressions still execute. |
| Arithmetic | Integer addition, subtraction, multiplication, and unary negation check for overflow. Division truncates toward zero. Division or remainder by zero faults. The minimum `I64` divided by −1 overflows. The corresponding remainder is zero. |
| Limits | The parser bounds nesting and expression height at 64. The interpreter defaults to one million steps and bounds evaluation nesting at 128. Set the step budget with `--fuel N`. Native programs use the host's resources and should be trusted. |

The compiler supports single-file scalar modules today. The [roadmap](../ROADMAP.md) tracks broader features such as imports, collections, payload-carrying variants, and capabilities.

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

## Verify a finite contract

A top-level `contract` declaration binds inputs and contains one Boolean expression. In this example a queue of eight items is full, so accepting one more would break the capacity rule.

```gpp
fn can_admit(queued: I64) -> Bool !{} {
    return queued < 8;
}

contract respects_capacity(queued: I64 in 0..=8) {
    can_admit(queued) == (queued + 1 <= 8)
}
```

Build the compiler and run the complete module from the repository root.

```sh
cargo build --locked --offline
target/debug/gpp verify examples/capacity.gpp --contract respects_capacity --format=json
```

The interval includes **both** endpoints. The verifier checks `queued = 0` through `queued = 8`. An `I64` binder requires literal bounds. A `Bool` binder takes `false` then `true`. With multiple binders the verifier checks their Cartesian product, varying the last binder fastest. A contract with `()` checks its predicate once. The predicate can call ordinary module functions, including unchanged callers of the function being edited. A passing report covers exactly the predicate and declared inputs. [Full module](../examples/capacity.gpp)

To see a counterexample, preview a change that also admits an item to a full queue.

```sh
printf '%s\n' 'queued <= 8' > target/full-queue.expr
target/debug/gpp edit examples/capacity.gpp --function can_admit \
  --expr target/full-queue.expr --stdout > target/full-queue.gpp
target/debug/gpp verify target/full-queue.gpp --format=json
```

At `queued = 8` the edited function returns true and the contract expects false. The following command checks the valid module with a budget of eight assignments. It reports an incomplete check because the ninth input is still outstanding.

```sh
target/debug/gpp verify examples/capacity.gpp --budget 8 --format=json
```

Without `--contract`, verification visits declarations in source order until all pass or the first failure or limit stops it. The default budget of 10,000 assignments is shared across selected contracts. `check` type-checks every predicate. Native builds omit the verification predicates, and running the program executes the ordinary `main`.

| `gpp.verify/1` status | Exit | Meaning |
|---|---:|---|
| `passed` | 0 | Every assignment in every selected contract completed with `true`. |
| `counterexample` | 1 | The first failing assignment returned `false` or raised an arithmetic fault. Its report includes named inputs, positional arguments and either the false result or the fault. |
| `incomplete` | 3 | The assignment budget or interpreter resource limit stopped verification, or the module has no contracts. The report gives the reason. |

The JSON includes the source revision and the number of assignments attempted. For the faulty queue, pass the witness directly to the tracer to see target values during evaluation of the predicate.

```sh
target/debug/gpp trace target/full-queue.gpp --function can_admit --contract respects_capacity 8
```

In the trace, the target expression `queued <= 8` returned `true` with `queued = 8`. The enclosing contract returned `false`. [Use contracts to select an edit](../tools/README.md#repair-an-expression-against-source-contracts)

### Require the proposed edit to pass

Add `--verify` to the ordinary checked-edit command to verify the exact proposed module before producing a preview or writing the source. For example, this command rejects the faulty expression from the walkthrough and reports the full-queue counterexample on stderr.

```sh
target/debug/gpp edit examples/capacity.gpp --function can_admit \
  --expr target/full-queue.expr --stdout --verify
```

For an in-place change, supply the original source revision with `--expect` and keep `--verify`. The verifier checks every declared contract on the proposed source, including contracts that exercise this function through a caller. A false predicate, arithmetic fault or incomplete verification rejects the edit before installation. Set `--budget N` alongside `--verify` to bound the shared assignment count. The default is 10,000. The apply command emitted by contract repair includes both the revision and verification budget.

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
| `--contract-cases FILE.tsv` | Use this option in place of `--cases`. Each row contains a contract name and in-domain arguments in declaration order. For `--filter`, append the expected Boolean result. The compiler evaluates the contract for each supplied tuple. |
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
