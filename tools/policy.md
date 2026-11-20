# Ordered scalar policies

A policy replaces one GPT++ function body. Each rule gives a condition and the value to return when it holds. The compiler checks the generated body against the existing declaration. The standalone tool runs locally with Python and the GPT++ compiler.

```text
when expedited and weight > 500 => 12
when expedited => 8
else => 4
```

## Rules and expressions

```ebnf
policy  = { guarded-row }, default-row ;
guarded-row = "when", whitespace, boolean-expression, "=>", result-expression ;
default-row = "else", "=>", (result-expression | "@keep") ;
```

Write one rule per line. Blank lines and whole-line `#` comments may appear anywhere. Rule text uses ASCII. Conditions run from top to bottom. Only the selected result expression runs. A policy can consist of a single default row. The policy source limit is 65,536 UTF-8 bytes.

Expressions can use typed parameters, signed integer literals, `True`, `False`, parentheses, comparisons, `and`, `or`, `not`, `+`, `-`, `*`, `//`, `%` and conditional values spelled `yes if condition else no`. Comparison chains support names or literals as intermediate operands. Conditions require booleans. Every returned expression must match the function's declared integer or boolean result, including branches that a particular input will skip.

Integer arithmetic uses checked signed 64-bit values. Division truncates toward zero and the remainder has the dividend's sign. Boolean operators and conditional values short-circuit. Integer `abs(x)`, `min(a, b)` and `max(a, b)` use the scalar translator's bounded expansion. Their operands are pure, and the selected operand may be evaluated again. Taking the absolute value of the smallest integer faults. [Scalar expression semantics](README.md#native-infill-and-python-syntax-fragments)

Use `else => @keep` for a maintenance change that adds exceptions to an existing implementation. When no guard matches, execution continues into the checked original body, including calls, local bindings and their original fault behavior. The compiler's normalized rendering of the target supplies this body in source mode. Comments inside the target can disappear during normalization. The ordinary name `keep` can still refer to a parameter.

## Preview, test and apply

Build the compiler with `cargo build --locked --offline`. For example, save these rules to `target/add.policy` to override the existing `add` function for negative first arguments.

```text
when left < 0 => right
else => @keep
```

Use a scratch copy to inspect the prospective change and execute the existing entry point.

```sh
cp examples/add.gpp target/add-base.gpp
python3 tools/policy_ir.py --source target/add-base.gpp --function add --preview \
  < target/add.policy > target/add-preview.gpp
target/debug/gpp run --interpreter target/add-preview.gpp
```

The original entry calls `add(20, 22)`, so this run prints `42` through the fallback. The offline test suite also exercises a changed input, short-circuiting, checked faults and preserved callers.

```sh
python3 -B tools/test_policy_ir.py
python3 tools/policy_ir.py --source target/add-base.gpp --function add --apply < target/add.policy
```

Each source-mode invocation reads a snapshot, derives the target's parameter and result types, and checks the edit against that snapshot's revision. To bind a separate later application to a previously reviewed revision, use the compiler's explicit revision guard.

```sh
base_revision=$(target/debug/gpp revision target/add-base.gpp)
python3 tools/policy_ir.py --source target/add-base.gpp --function add \
  < target/add.policy > target/add.body
target/debug/gpp edit target/add-base.gpp --function add --body target/add.body \
  --expect "$base_revision" --stdout
```

Review the printed module and remove `--stdout` to apply that exact fragment with the same revision guard.

## Standalone lowering

Supply parameter and result types explicitly to emit a bare body for a new function. The result defaults to `int`. Standalone policies require an explicit fallback expression.

```sh
echo 'else => abs(value)' | python3 tools/policy_ir.py --param value:int
```

Python callers with `tools` on their module search path can use `lower_policy(text, params, result="int", *, original_body=None)`. Each parameter is a `(name, "int" | "bool")` pair. Pass the checked target's bare GPT++ body as `original_body` to enable `@keep`. Invalid policies raise `ValueError` before generating an edit.
