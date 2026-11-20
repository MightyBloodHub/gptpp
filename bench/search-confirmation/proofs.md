# Symbolic checks of the two additional correct completions

GPT++ solved two exercises that the largest portable minimum-cost search missed. The runner reproduced each GPT++ completion from its original sketch and 24 public examples, confirmed that it matched the archived selection, and then appended an independent full-width contract. Z3 4.16.0 proved both contracts. Applying the same contracts to the defective starter expressions produced two counterexamples that the GPT++ interpreter replayed. [Generated expressions and solver reports](proofs.json) · [Paired benchmark results](results.md)

| Exercise | What the proof covers |
| --- | --- |
| `specialEleven` | For every nonnegative signed 64-bit integer, the selected expression accepts exactly the values with remainder zero or one on division by eleven. |
| `sumDouble` | For every signed 64-bit input pair whose specified mathematical result fits I64, the generated function returns the sum for unequal inputs and twice the sum for equal inputs. |

For `sumDouble`, the contract checks unequal inputs whenever their sum fits. For equal inputs, the mathematical result is four times the common value, so the contract checks values from −2,305,843,009,213,693,952 through 2,305,843,009,213,693,951 inclusive. The obligations were written after the benchmark and supplied only to the proof command. The two additional wins were identified from the entire paired comparison before running these proofs.

## Run the search and proofs

Use the pinned Rust toolchain, Python 3 and Z3 on the command search path.

```sh
cargo build --release --locked --offline
python3 -B bench/search-confirmation/prove_wins.py
```

The program writes temporary modules and uses the same shipped `complete` and `prove` commands as a regular client. Solver proofs depend on the compiler's translation and Z3. The archived finite trials for all eleven exercises remain available independently. [Proof runner and exact predicates](prove_wins.py) · [Symbolic verifier validation](../proof/README.md)
