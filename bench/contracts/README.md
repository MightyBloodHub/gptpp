# Finite contracts

Three small scalar programs have executable GPT++ contracts over fixed input domains. The report compares sparse-example filtering with full-domain verification, checks the first counterexamples against independent arithmetic oracles, and records each search result. The companion Python and Rust programs execute the same candidate expressions on all the same inputs, including inputs outside the contract used to illustrate the limits of a bounded guarantee. All local compiler and language commands run without model inference. [Report](results.md) · [Protocol](protocol.md) · [Frozen fixture definitions](fixtures.py) · [Raw records](results.jsonl)

From the repository root, build GPT++ with the pinned Rust toolchain. The study requires Python 3.10 or newer and `rustc` on the search path. Generating the Markdown report reads the archived results without executing the compilers.

```sh
cargo build --locked --offline
python3 -B bench/contracts/study.py --report bench/contracts/results.jsonl
python3 -B bench/contracts/study.py --replay bench/contracts/results.jsonl
```

To collect fresh records, invoke the same script with a new output path. The first JSONL record fingerprints the fixture, tools, compiler sources and binary. Each remaining record contains the original module, candidate edits, direct-call outcomes, checked verification reports, search results and budget-boundary outcomes for one task. A shared direct-outcome fingerprint for each language lets readers confirm parity. Replay tolerates a different compiler binary layout when the sources and observed results match.

## Model-generated expressions

A supplemental study used the contract-mode agent editor to generate an expression and request up to one retry. Qwen repaired the capacity predicate, and StarCoder2 produced no verified repair in its three trials. The six archived assignments account for every reported token within those assignments. The report records a separate interrupted collection whose token usage was unavailable. [Model results](model-results.md) · [Model protocol](model-protocol.md) · [Prompts and responses](model-results.jsonl)

```sh
python3 -B bench/contracts/model_study.py --report bench/contracts/model-results.jsonl
python3 -B bench/contracts/model_study.py --replay bench/contracts/model-results.jsonl
```

The replay uses archived completions and the real compiler and CLI. A fresh collection requires the two pinned local Ollama models and a new output path.
