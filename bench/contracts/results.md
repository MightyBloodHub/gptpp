# Finite contracts and checked repairs

Three locally authored contracts cover 73 distinct input tuples. Two visible examples per task admit several wrong edits. We independently executed every curated candidate and starter in GPT++, Python and Rust and checked all returned values and faults.

| Task | Domain tuples | First starter counterexample | Curated edits passing examples | Edits passing full contract | Contract menu |
|---|---:|---|---:|---:|---|
| offset_tick | 16 | `(-3, true)` false predicate | 4 | 2 | ambiguous |
| has_room | 25 | `(0, 0)` false predicate | 3 | 1 | verified |
| block_index | 32 | `(0, 0)` DivisionByZero | 3 | 1 | verified |

The exact-domain checks rejected 6 of the 10 curated edits that passed their sparse examples. All three language implementations agreed on 373 program/input outcomes per language, including the separate out-of-domain checks.

| Task | First example-search candidate | First certified substitution | Edits tried by contract search |
|---|---|---|---:|
| offset_tick | fails full domain | `offset` → `offset + (if carry { 1 } else { 0 })` | 3 |
| has_room | passes full domain | `used` → `used + 1` | 2 |
| block_index | passes full domain | `last_lane` → `last_lane + 1` | 3 |

The contract-guided search certified edits on 3/3 tasks. Taking the first edit found by the sparse-example search passed the full domain on 2/3. Those two searches also differ in mutation order and available substitutions. Only the curated-menu comparison holds the candidate set fixed.

The two carry edits that pass the declared domain differ outside it. The deliberately capped candidate misses three of five extra probes. The menu preserves that ambiguity. The synthesis column reports the first certified candidate in search order.

Across all three tasks, a verified patch checked with a budget one below its domain size returned incomplete. Raising the budget by one verified the complete domain. Each short-budget repair run left its output fragment absent. No model calls were made. The study measures bounded correctness and counterexample reporting. Its hand-authored candidate menus leave model repair accuracy unmeasured.
