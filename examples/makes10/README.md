# A public symmetry rule catches the makes10 edit

The sketch is the exact historical revision `f6051417…` with its 24 public examples. Its piecewise edit accepts pairs that sum to ten and pairs with ten on the right. An independently declared contract calls the function twice with its arguments interchanged. Exhaustive enumeration over each argument in `-5..=18` stops after 16 pairs. The interpreter evaluates `transition(-5, 10)` to true and `transition(10, -5)` to false. A revision-bound `probe` and a compiler trace both reproduce the failure. These calls, including the historical scoring witness, are development data.

| Candidate and predeclared gate | Public examples | Outcome |
| --- | --- | --- |
| Archived piecewise edit, symmetry and exact rule | 24/24 | Rejected at the symmetry counterexample. |
| Correct reference, same gate | 24/24 | Checked all 576 pairs for symmetry. Z3 proved the exact rule over those same 576 pairs. |
| Archived piecewise edit, weak right-ten gate | 24/24 | Accepted. The report lists the 24 assignments with ten on the right and the missing constraint in `limitation`. |
| New Qwen repair, symmetry and exact rule | 0/1 checked | Rejected on the first public example. Further checks remained pending. |

The actual repair request included the previous expression, its type and local variables, the public interchangeability rule and both observed calls. Qwen proposed `(a + b == 10) || (a == 10)`, which drops the previous right-ten case. The public gate rejected that replacement on `(9,10)`. The single generation used 185 input and 24 output tokens and took 7.69 seconds. The historical direct Qwen response had already solved this exercise. The newly executed repair provides a failed development trial, outside fresh comparison totals. [Full development receipt](development.json)

## Replay the development demonstration

From the repository root, use Python 3, the pinned Rust toolchain and Z3 on the command search path.

```sh
cargo build --release --locked --offline
python3 -B examples/makes10/demo.py
```

The default command rechecks both controls and the weak contract, reruns piecewise search and replays the saved model response after verifying its request. To collect another explicitly labeled live trial with local Ollama, use `--live --output target/makes10-new.json`.

## Use the opt-in gate on a public sketch

```sh
python3 -B tools/acceptance.py examples/makes10/public.gpp \
  --contracts examples/makes10/contracts.json \
  --task 'Accept when either argument is ten or their sum is ten.' \
  --model qwen2.5-coder:7b
```

Provide a sketch with one typed expression hole, optional public example contracts and a JSON list of acceptance obligations. Each obligation carries its GPT++ declaration, name, human-readable rule, mode (`finite` or `prove`) and an optional limitation. With no examples it records `not_provided` and zero checked labels. The type check uses one internal constant predicate on a temporary copy. The command emits the selected expression and evidence as JSON. The candidate records distinguish the result of checking a single expression from the final decision to publish. Skipping `--model` runs the compiler-only path. Supply `--reference FILE` only to authorize a total GPT++ implementation of the same function and parameter order to answer one distinguishing input. A finite agreement that leaves both alternatives viable without an authorized answer produces an abstention.

The gate checks the original typed hole at its source revision, replays public examples, then runs each named obligation. A failed example or property may trigger one model repair. A proof timeout, unsupported obligation or exhausted finite budget leaves that candidate unverified. A failing caller whose condition never evaluates the slot can have an empty observation list. The `observed` field contains up to three actual visits to the authorized expression. [Gate and policy implementation](../../tools/acceptance.py) · [Executable ambiguity, timeout, proof and budget tests](../../tools/test_acceptance.py)
