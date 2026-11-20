# Checkout shipping-fee calibration

## Maintenance task

Change `shipping_fee(subtotal_cents, member, pickup)` so members get free delivery starting at **5,000 cents**, inclusive. Keep the existing 299-cent member fee below that threshold. Ordinary delivery still costs 599 cents below 7,500 cents and is free from 7,500 cents. Pickup is always free. Preserve the function signature. Inputs are whole subtotals from 0 through 1,000,000 cents inclusive and two booleans.

## Offline check

From the repository root, run the following command with Python 3, Rust and Cargo installed.

```sh
python3 bench/pilot/calibrate.py
```

The three starters implement the old policy. Each row in `cases.tsv` supplies hand-written expected fees before and after the change. The checker executes each starter, applies a reviewed one-condition edit to a temporary copy, and executes it again. Python uses its annotated function, Rust uses a compiled binary, and GPT++ uses the bootstrap interpreter. The fixed input range keeps the integer calculations equivalent across languages.

The starter must fail the three new member-delivery cases and preserve all ten other cases. The repair must pass all thirteen. The command exits with a failure if any individual observation differs.

## Before an authoring experiment

These fixtures and repairs are public development examples. Keep them outside qualification sets. Before measuring an authoring advantage, create independent held-out task families and tests, freeze model versions, prompts, tool access and repair budgets, and run paired trials against ordinary and enhanced existing-language tooling. Record actual model usage, tool compute, failures and acceptance for every attempt. This calibration records only fixture behavior.
