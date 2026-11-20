# Archived public caller failures and exact obligations

These are retrospective coverage results across all v5 and v6 arms. Each assigned task and arm contributes its first attempt. A repeated failure means that several arms failed the same first public assertion on the same task.

| Study | Assignments | Public pass | Check error | Target mismatch | Caller mismatch | Distinct caller cases | Exact per arm | Exact per case |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| v5 | 40 | 19 | 3 | 13 | 5 | 3 | 0 | 0 |
| v6 | 40 | 10 | 0 | 4 | 26 | 9 | 10 | 4 |

| Study | Public caller assertion | Arms | Derived target obligation or reason | Target differs from starter | Already public directly |
|---|---|---:|---|---|---|
| v5 | `week_start(-1, true) = -4` | 2 | operation needs a concrete value | — | — |
| v5 | `weekend_badge(-5) = 1` | 1 | operation needs a concrete value | — | — |
| v5 | `review_flag(0, 2147483648) = 1` | 2 | operation needs a concrete value | — | — |
| v6 | `available_cash(200, 1, 0, true) = 200` | 4 | operation needs a concrete value | — | — |
| v6 | `settlement_day_number(10, 3, false) = 14` | 1 | settlement_lag(3, false) = 4 | No | No |
| v6 | `branches_in_plan(3, true, true, true, false) = 1` | 5 | multiple distinct target argument tuples | — | — |
| v6 | `strip_width(100, 70, 6, 2) = 148` | 1 | display_width(100, 70, 6) = 70 | No | No |
| v6 | `panel_route(0, 0, false, 2) = 2` | 1 | operation needs a concrete value | — | — |
| v6 | `wait_minutes(24, 10, 1435) = 15` | 5 | operation needs a concrete value | — | — |
| v6 | `page_offset(1, 3) = 131072` | 1 | operation needs a concrete value | — | — |
| v6 | `advance_offset(7, 55296) = 7` | 3 | utf16_units(55296) = 0 | No | No |
| v6 | `violations_in_group(3, 23, 40, false, true) = 3` | 5 | passes_size(23, 40, false, true) = 0 | Yes | No |

4 of 12 distinct caller assertions yielded an exact obligation (10 of 31 arm-level failures). All derivations ran before the post hoc reference comparisons. 4 of 4 distinct results matched the frozen Python target at the derived input. 4 inferred target values differed numerically from the caller expectation. 0 obligations duplicated a direct public target assertion.

Reading the eight declined caller paths identifies six that compare the unknown target result before choosing a branch, one that takes the unknown modulo seven, and one that combines two distinct target inputs. Some guarded paths could still admit an exact solution. For example, the DNS review flag equals one only when the serial ordering result equals two. The current affine analysis declines that comparison.

The audit supplied each obligation process with the checked baseline GPT++ module and one recorded public assertion. It used the frozen reference and starter afterward to check agreement and identify changed results. All 19 extra arm-level observations repeat one of the 12 caller assertions. Repair effectiveness requires a prospective trial.

Reproduce with `python3 -B bench/policy/audit_obligations.py` after building the [obligation CLI](../../tools/caller_obligation.md). [v5 raw trials](../maintenance/results/maintenance.jsonl) · [v6 raw trials](../adaptive/results/adaptive.jsonl)
