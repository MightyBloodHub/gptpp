# Matched state-transition edits

The study gives two local models the same four maintenance requests in GPT++, typed Python and Rust. A protected event handler has a single typed expression hole. GPT++ uses its compiler’s hole-filling interface; Rust and Python use adapters with the same edit scope, sequence contracts, feedback policy, expression restrictions and two-call limit. A separate no-model comparison holds candidate order fixed across all three languages. [Results](results.md) · [Paired wins, losses and cost](paired.md) · [Pre-inference protocol](protocol.md) · [Corpus and independent oracles](tasks.py) · [Freeze and timing record](freeze.json)

Qwen repaired the reading-marker and streak cases in each native language. StarCoder2 returned the literal schema illustration `one native expression` on all 24 of its attempts, which the expression validator rejected before compilation. Its small validation times reflect these early rejections. The model-free grammar solved the marker, pair-dispatch and armed-toggle cases in each language. GPT++’s separate automatic completion solved the first two of those. [Replay Qwen’s streak expression through the compiler and native Python client](../../examples/streak_counter/README.md)

## Reproduce

Use the pinned local Rust toolchain and the Python 3.11 benchmark environment with mypy 1.15.0. The comparison uses a writable temporary directory for isolated checkers and a new output path for live collection. Inference calls Ollama on loopback. Reproducing the report and replaying archived replies require no model server. [Python environment setup](../empirical/README.md#reproduce)

```sh
cargo build --locked --offline
python3 -B bench/stateful/compare.py --preflight bench/stateful/results.jsonl
python3 -B bench/stateful/compare.py --report bench/stateful/results.jsonl
python3 -B bench/stateful/paired.py bench/stateful/results.jsonl
python3 -B bench/stateful/compare.py --replay bench/stateful/results.jsonl
```

For fresh inference use the two model digests in the manifest. The collector saves each original response, prompt and usage immediately, before validation. A fresh path avoids overwriting the published archive. Rerunning the same collection path recovers journaled calls and skips completed trials; a source or binary fingerprint mismatch stops collection.

```sh
python3 -B bench/stateful/compare.py target/stateful-new.jsonl
```

The [raw archive](results.jsonl) has one manifest, a row per model call, one outcome per assigned trial and four no-model controls per family. Each trial records public diagnostics, per-attempt validation time, end-to-end workflow time, and a separate timed hidden score on published patches. For GPT++ the validator checks the compiler's native full-module fill result. It independently runs visible calls to normalize counterexample feedback. Rust uses overflow-checked `rustc` builds. Python uses strict mypy, guarded expression parsing and native execution. Each observer evaluates full end states on the same ordered inputs. Captured compiler provenance is in [compiler-capture.json](compiler-capture.json).

Each task family uses different transitions, its own initial state, a fixed set of visible event words and an independent history-level oracle. Every other event word of length 1 through 6 is scored. The benchmark has four independent task families. It does not establish behavior on arbitrary sequence lengths, multi-file edits, networked systems, or other models. These tasks were kept from the product implementers until the compiler and completion interface were frozen. Local measurements include actual checker/cache and process overhead. They are descriptive on this development host.

One observer import was restored during initial collection, before any Python trial had a scored result. The journal preserved every earlier response and completed trial. The manifest records the original prefix hash and source identities. No inference was repeated for that correction. The 173.764-second authoring interval covers writing and freezing the shared task definitions, test-oracle designs and protocol. It excludes initial discussion, harness implementation, preflight, model inference and validation. It is agent wall time, without a measurement of human labor.

The release compiler includes a subsequent ambiguity-check fix. A full offline replay with that build reproduced the 24 native trials, all 42 original model requests, the 12 shared-grammar controls and the four automatic compiler selections. The native Python example also passed on that build. [Replay record and both compiler fingerprints](release-replay.json)
