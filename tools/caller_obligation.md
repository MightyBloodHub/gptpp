# Deriving a target result from a public caller test

Suppose a public test expects `invoice(4)` to return 26. If the unchanged caller returns `30 - 2 * discount(4)`, that example requires `discount(4)` to return 2. `caller-obligation` obtains this requirement from the checked GPT++ caller and the supplied public expectation. Each result applies to exactly one argument tuple.

Build the standalone tool from the repository root with the project’s Rust toolchain. It uses the existing compiler modules and the Rust standard library.

```sh
mkdir -p target
rustc --edition=2024 -O tools/caller_obligation.rs -o target/caller-obligation
```

For example, save this module as `invoice.gpp`.

```gpp
module billing;
fn discount(items: I64) -> I64 !{} { return 0; }
fn invoice(items: I64) -> I64 !{} { return 30 - 2 * discount(items); }
pub fn main() -> I64 !{} { return 0; }
```

```sh
target/caller-obligation invoice.gpp --caller invoice --target discount --expect 26 -- 4
```

```json
{"status":"exact","target":"discount","args":[4],"expected":2}
```

Use the options in the order shown. After `--`, pass one decimal I64 or lowercase `true` or `false` per caller parameter. The file must be a valid scalar module with the normal executable entry. Exit status 0 produces one JSON object. An `unsupported` object contains a short `reason` and offers no result to inject. File, declaration, caller argument and type-checking errors produce a diagnostic on standard error and exit status 2.

The caller-test runner owns the failure trigger. It can pass a read-only module with the same unchanged caller and helpers across languages. The target implementation is type-checked with the whole module and treated as unknown during analysis. Its prior behavior does not affect the obligation. The tool uses only the arguments and expected result supplied to this invocation. A passing edit still needs to satisfy the remaining tests.

## Supported cases

The tool walks the verified control-flow graph, evaluating scalar helpers, branches and loops along the supplied input’s concrete path. A target invocation with concrete arguments introduces an unknown integer. Repeated invocations of that same tuple share a value. Addition, subtraction, negation, multiplication by a concrete integer and division by 1 or −1 preserve the affine expression. The tool solves the resulting integer equation and replays the caller with the proposed target value, including every checked arithmetic intermediate. The caller and target must both return I64.

An `unsupported` result covers multiple distinct target tuples, comparisons involving the unknown, nonlinear operations, ambiguous or nonintegral solutions, arithmetic faults, and resource limits. A zero coefficient gives no unique answer. The module size limit is 65,536 UTF-8 bytes. Each execution has 16,384 steps and a maximum call depth of 32. An otherwise valid relation can exceed these bounds or the internal checked 128-bit coefficient range.

Run the tests, including a differential check against the source-tree interpreter, from the repository root.

```sh
rustc --edition=2024 --test tools/caller_obligation.rs -o target/caller-obligation-tests
target/caller-obligation-tests
```
