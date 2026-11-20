# Multi-caller maintenance benchmark

All 40 trials completed across 8 task families and five conditions on qwen2.5-coder:7b. The 28 public and 128 hidden cases exercised both the edited targets and unchanged callers.

An accepted change passes the checker and both test groups. Reported tokens include the rendered model input, generated output, failed attempts and repairs. Workflow time includes model calls and public checks. Held-out scoring time is recorded separately.

## Matched workflows

| Condition | Workflow |
|---|---|
| gpp_context | GPT++ with caller context |
| python_context | Typed Python with caller context |
| rust_context | Rust with caller context |
| gpp_target | GPT++ target only |
| gpp_projected | GPT++ from Python syntax with caller context |

| Condition | Calls | First accepted | Accepted | Input tokens | Output tokens | Total tokens | Tokens/accepted | Workflow s/accepted |
|---|---|---|---|---|---|---|---|---|
| gpp_context | 13 | 3/8 (37.5%) | 4/8 (50.0%) | 6536 | 864 | 7400 | 1,850.00 | 12.11 |
| python_context | 10 | 6/8 (75.0%) | 6/8 (75.0%) | 4100 | 462 | 4562 | 760.33 | 7.47 |
| rust_context | 12 | 3/8 (37.5%) | 3/8 (37.5%) | 5640 | 733 | 6373 | 2,124.33 | 24.74 |
| gpp_target | 13 | 3/8 (37.5%) | 4/8 (50.0%) | 4483 | 819 | 5302 | 1,325.50 | 10.94 |
| gpp_projected | 13 | 3/8 (37.5%) | 3/8 (37.5%) | 6644 | 754 | 7398 | 2,466.00 | 14.96 |

## Paired estimates

Brackets are 95% percentile intervals from 10,000 task resamples. The acceptance interval must start at −2 percentage points or higher and the tokens-per-accepted interval must end at 0.80 or lower to meet both criteria.

| Numerator | Comparator | Matched | Tasks | Acceptance Δ (pp) | All-token ratio | Tokens/accepted ratio | Workflow s/accepted ratio | Thresholds |
|---|---|---|---|---|---|---|---|---|
| gpp_context | python_context | 8/8 | 8 | -25.0000 [-62.5000, 0.0000] | 1.6221 [1.1666, 2.1998] | 2.4331 [1.1601, 7.5171] (37 undefined draws) | 1.6210 [0.8939, 4.2616] (37 undefined draws) | bounds not both met |
| gpp_context | rust_context | 8/8 | 8 | 12.5000 [0.0000, 37.5000] | 1.1611 [1.0541, 1.4329] | 0.8709 [0.0000, ∞] (252 undefined draws) | 0.4892 [0.0000, ∞] (252 undefined draws) | bounds not both met |
| gpp_context | gpp_target | 8/8 | 8 | 0.0000 [-37.5000, 37.5000] | 1.3957 [1.0618, 1.7859] | 1.3957 [0.3989, 3.9337] (75 undefined draws) | 1.1060 [0.3059, 3.1052] (75 undefined draws) | bounds not both met |
| gpp_projected | python_context | 8/8 | 8 | -37.5000 [-75.0000, 0.0000] | 1.6217 [1.1652, 2.2039] | 3.2433 [1.1321, 19.3933] (220 undefined draws) | 2.0026 [0.7356, 10.4480] (220 undefined draws) | bounds not both met |
| gpp_projected | rust_context | 8/8 | 8 | 0.0000 [-37.5000, 37.5000] | 1.1608 [1.0463, 1.4398] | 1.1608 [0.0000, ∞] (435 undefined draws) | 0.6044 [0.0000, ∞] (435 undefined draws) | bounds not both met |

## Distance to the 20% target

These are observed point estimates. The last column keeps token spending fixed and applies both the token target and the acceptance margin to the observed comparator.

| GPT++ workflow | Comparator | Target tokens/accepted | Observed cost ratio | Gap above target (pp of baseline) | Required token cut at observed acceptance (%) | Minimum accepts at observed spending |
|---|---|---|---|---|---|---|
| gpp_context | python_context | 608.27 | 2.433 | 163.3 | 67.1 | 13 required with 8 assigned |
| gpp_context | rust_context | 1,699.47 | 0.871 | 7.1 | 8.1 | 5 |
| gpp_projected | python_context | 608.27 | 3.243 | 244.3 | 75.3 | 13 required with 8 assigned |
| gpp_projected | rust_context | 1,699.47 | 1.161 | 36.1 | 31.1 | 5 |

## Cost of the public-feedback repair

The first-call columns count the observed initial calls and their acceptance. The repair columns count the additional calls, tokens and accepted trials.

| Condition | First-call tokens | First accepted | First-call tokens/accepted | Repair calls | Additional tokens | Additional accepted |
|---|---|---|---|---|---|---|
| gpp_context | 4155 | 3 | 1,385.00 | 5 | 3245 | 1 |
| python_context | 3560 | 6 | 593.33 | 2 | 1002 | 0 |
| rust_context | 3908 | 3 | 1,302.67 | 4 | 2465 | 0 |
| gpp_target | 2936 | 3 | 978.67 | 5 | 2366 | 1 |
| gpp_projected | 4177 | 3 | 1,392.33 | 5 | 3221 | 0 |

## Outcomes by task

| Task | gpp_context | python_context | rust_context | gpp_target | gpp_projected |
|---|---|---|---|---|---|
| usps_retail_tariff | accepted | accepted | accepted | accepted | accepted |
| s3_small_object_default | accepted | accepted | accepted | accepted | accepted |
| kube_backoff_gate | accepted | accepted | accepted | accepted | check_error |
| ifab_substitution_windows | wrong_answer | accepted | wrong_answer | wrong_answer | wrong_answer |
| archive_calendar | wrong_answer | wrong_answer | wrong_answer | accepted | wrong_answer |
| wave_preview | accepted | accepted | heldout_wrong_answer | wrong_answer | accepted |
| dns_zone_serial | wrong_answer | accepted | wrong_answer | wrong_answer | wrong_answer |
| download_byte_ranges | heldout_wrong_answer | wrong_answer | wrong_answer | wrong_answer | wrong_answer |

## Failure diagnostics

| Condition | Stage | Result | Count |
|---|---|---|---|
| gpp_context | held-out | heldout_wrong_answer | 1 |
| gpp_context | public | wrong_answer | 3 |
| gpp_projected | patch | check_error | 1 |
| gpp_projected | public | wrong_answer | 4 |
| gpp_target | public | wrong_answer | 4 |
| python_context | public | wrong_answer | 2 |
| rust_context | held-out | heldout_wrong_answer | 1 |
| rust_context | public | wrong_answer | 4 |

Wrong-output diagnostics identify the first failing call in the tested group.

| Condition | Stage | First failing entry | Terminal trials |
|---|---|---|---|
| gpp_context | held-out | target | 1 |
| gpp_context | public | caller | 1 |
| gpp_context | public | target | 2 |
| gpp_projected | public | caller | 2 |
| gpp_projected | public | target | 2 |
| gpp_target | public | caller | 1 |
| gpp_target | public | target | 3 |
| python_context | public | caller | 1 |
| python_context | public | target | 1 |
| rust_context | held-out | target | 1 |
| rust_context | public | caller | 2 |
| rust_context | public | target | 2 |

| Condition | Attempts with an explicit output-boundary error |
|---|---|
| gpp_context | 0 |
| python_context | 0 |
| rust_context | 0 |
| gpp_target | 0 |
| gpp_projected | 0 |

## Change provenance

- **usps_retail_tariff**. Application-style mailroom fixture derived from the July 14, 2024 USPS Notice 123 retail rate table. The date flag, mixed-mail batch and postage-due calculation are local application code. [Primary source](https://pe.usps.com/Archive/NHTML/DMMArchive20240714/Notice123.htm)

- **s3_small_object_default**. Application-style S3 lifecycle planner reproducing the September 2024 change to the default minimum transition size and the documented behavior of grandfathered configurations. [Primary source](https://docs.aws.amazon.com/AmazonS3/latest/userguide/lifecycle-transition-general-considerations.html)

- **kube_backoff_gate**. Application-style restart scheduler and incident timeline. The two delay sequences reproduce Kubernetes v1.33's ReduceDefaultCrashLoopBackOffDecay feature gate, with no node-level overrides. [Primary source](https://v1-33.docs.kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/)

- **ifab_substitution_windows**. Application-style team-sheet editor reproducing the IFAB 2022/23 optional five-substitute rule. This fixture covers normal time only, with no concussion substitutes. [Primary source](https://www.theifab.com/news/the-ifab-permanently-approves-five-substitute-option-in-top-level-competitions/)

- **archive_calendar**. The ISO weekday numbering follows Python's documented date.isoweekday contract. The archival import, epoch-offset interface and layout callers are authored scenarios. [Primary source](https://docs.python.org/3/library/datetime.html#datetime.date.isoweekday)

- **wave_preview**. Microsoft documents signed 16-bit PCM and unsigned 8-bit PCM including their midpoints. Truncating the biased value to its high byte is this exporter's quantizer policy. [Primary source](https://learn.microsoft.com/en-us/windows/win32/multimedia/devices-and-data-types)

- **dns_zone_serial**. RFC 1982 defines finite serial comparison and leaves half-range comparisons undefined. Status 2 and manual approval are conventions of this authored zone publisher. [Primary source](https://www.rfc-editor.org/rfc/rfc1982.html#section-3.2)

- **download_byte_ranges**. RFC 9110 sections 14.1.1–14.1.2 define single suffix ranges, oversize handling and satisfiability on empty representations. The -1 sentinel and streaming callers are local. [Primary source](https://www.rfc-editor.org/rfc/rfc9110.html#section-14.1.2)
