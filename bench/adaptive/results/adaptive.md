# Adaptive caller-context benchmark

40 matched trials on 8 new tasks with qwen2.5-coder:7b. The harness scored 31 public and 124 withheld cases. An accepted patch must pass both. The token budget counts the full input and generated output of every call, including unsuccessful calls and repairs.

## Acceptance and usage

| Workflow | Calls | First accepted | Accepted | Input tokens | Output tokens | Total tokens | Tokens/accepted | Workflow seconds/accepted |
|---|---|---|---|---|---|---|---|---|
| GPT++ adaptive | 14 | 2/8 (25.0%) | 2/8 (25.0%) | 5349 | 562 | 5911 | 2,955.50 | 17.10 |
| Typed Python adaptive | 13 | 3/8 (37.5%) | 3/8 (37.5%) | 4351 | 473 | 4824 | 1,608.00 | 13.92 |
| Rust adaptive | 15 | 1/8 (12.5%) | 1/8 (12.5%) | 5609 | 737 | 6346 | 6,346.00 | 90.33 |
| GPT++ target only | 14 | 2/8 (25.0%) | 2/8 (25.0%) | 4629 | 561 | 5190 | 2,595.00 | 15.05 |
| GPT++ caller context always | 14 | 2/8 (25.0%) | 2/8 (25.0%) | 6584 | 539 | 7123 | 3,561.50 | 16.47 |

## Retry behavior

| Workflow | Retries | First public failure at caller | Retries with excerpts | Accepted with excerpts on retry | Accepted without excerpts on retry | Retry tokens |
|---|---|---|---|---|---|---|
| GPT++ adaptive | 6 | 5 | 5 | 0 | 0 | 3158 |
| Typed Python adaptive | 5 | 5 | 5 | 0 | 0 | 2404 |
| Rust adaptive | 7 | 6 | 6 | 0 | 0 | 3754 |
| GPT++ target only | 6 | 5 | 0 | 0 | 0 | 2437 |
| GPT++ caller context always | 6 | 5 | 6 | 0 | 0 | 3221 |

## Paired estimates

Brackets are 95% percentile intervals from 10,000 task-cluster resamples. The lower acceptance bound must be at least −2 percentage points. The upper cost-ratio bound must be at most 0.80. Workflow time covers inference and public checks.

| Comparator | Matched | Tasks | Acceptance Δ (pp) | Total token ratio | Tokens/accepted ratio | Workflow time/accepted ratio | Thresholds |
|---|---|---|---|---|---|---|---|
| python_adaptive | 8/8 | 8 | -12.5000 [-37.5000, 0.0000] | 1.2253 [1.0486, 1.6021] | 1.8380 [0.0000, ∞] (1031 undefined draws) | 1.2283 [0.0000, ∞] (1031 undefined draws) | bounds not both met |
| rust_adaptive | 8/8 | 8 | 12.5000 [0.0000, 37.5000] | 0.9315 [0.7539, 1.0512] | 0.4657 [0.0000, ∞] (3389 undefined draws) | 0.1893 [0.0000, ∞] (3389 undefined draws) | bounds not both met |
| gpp_target | 8/8 | 8 | 0.0000 [0.0000, 0.0000] | 1.1389 [1.0667, 1.1915] | 1.1389 [0.0000, ∞] (1031 undefined draws) | 1.1364 [0.0000, ∞] (1031 undefined draws) | bounds not both met |
| gpp_context | 8/8 | 8 | 0.0000 [-37.5000, 37.5000] | 0.8298 [0.6244, 1.0900] | 0.8298 [0.0000, ∞] (1801 undefined draws) | 1.0379 [0.0000, ∞] (1801 undefined draws) | bounds not both met |

## Distance to the 20% goal

The table uses observed point estimates against the same adaptive policy. The required token reduction keeps GPT++ acceptance fixed. Required accepts keep GPT++ token spending fixed and apply both point targets.

| Comparator | 20% target tokens/accepted | Observed GPT++ cost ratio | Gap above 0.80 (pp of comparator) | Acceptance Δ (pp) | Further token cut (%) | Accepted edits required at observed spending |
|---|---|---|---|---|---|---|
| Typed Python adaptive | 1,286.40 | 1.838 | 103.8 | -12.5 | 56.5 | 5 |
| Rust adaptive | 5,076.80 | 0.466 | -33.4 | 12.5 | 0.0 | 2 |

## Task outcomes

| Task | gpp_adaptive | python_adaptive | rust_adaptive | gpp_target | gpp_context |
|---|---|---|---|---|---|
| git_push_default | wrong_answer | wrong_answer | wrong_answer | wrong_answer | wrong_answer |
| mode_tie_order | wrong_answer | wrong_answer | wrong_answer | wrong_answer | wrong_answer |
| equity_settlement_cycle | wrong_answer | wrong_answer | wrong_answer | wrong_answer | wrong_answer |
| wcag22_target_size | wrong_answer | wrong_answer | wrong_answer | check_error | wrong_answer |
| night_service_board | wrong_answer | wrong_answer | wrong_answer | wrong_answer | wrong_answer |
| sqlite_page_header | accepted | accepted | wrong_answer | accepted | accepted |
| mirrored_gallery_layout | accepted | accepted | accepted | accepted | wrong_answer |
| utf16_editor_offsets | wrong_answer | accepted | wrong_answer | wrong_answer | accepted |

## Same initial prompt in GPT++

The adaptive and target-only arms start with identical prompt and sampling settings. The table shows tasks that triggered excerpts in the adaptive arm. A changed first reply can contribute to a changed final result.

| Task | Caller that triggered context | Same initial reply | Adaptive final outcome | Target-only final outcome |
|---|---|---|---|---|
| git_push_default | branches_in_plan | yes | wrong_answer | wrong_answer |
| equity_settlement_cycle | available_cash | yes | wrong_answer | wrong_answer |
| wcag22_target_size | violations_in_group | yes | wrong_answer | check_error |
| night_service_board | wait_minutes | yes | wrong_answer | wrong_answer |
| utf16_editor_offsets | advance_offset | yes | wrong_answer | wrong_answer |

## Change provenance

- **git_push_default**. Application-style push preview based on Git 2.0's change of push.default from matching to simple. This fixture considers existing same-name destinations on the fetch remote; no refspec or branch creation. [Primary source](https://github.com/git/git/blob/v2.0.0/Documentation/RelNotes/2.0.0.txt)

- **mode_tie_order**. An authored two-category analytics dashboard reproduces the Python 3.8 statistics.mode tie change. The dashboard maps StatisticsError to the existing code 0. [Primary source](https://docs.python.org/3.8/library/statistics.html#statistics.mode)

- **equity_settlement_cycle**. An authored brokerage ledger reproduces the US transition from T+2 to T+1 on May 28, 2024. The fixtures cover regular-way stock trades and intervals without market holidays. [Primary source](https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins/new-t1-settlement-cycle-what-investors-need-know-investor-bulletin)

- **wcag22_target_size**. An authored audit tool follows the new WCAG 2.2 Level AA success criterion 2.5.8 and existing AAA criterion 2.5.5. Inputs are rectangular authored targets with no applicable exceptions. [Primary source](https://www.w3.org/TR/2023/REC-WCAG22-20231005/#target-size-minimum)

- **night_service_board**. GTFS Schedule permits departures after midnight to retain hours of 24 or greater on the originating service day. The 47-hour cap, minute precision, wait display and day badge are conventions of this authored application. [Primary source](https://gtfs.org/documentation/schedule/reference/#stop_timestxt)

- **sqlite_page_header**. SQLite documents a file-format change in version 3.7.1 permitting a 65536-byte page via a special header word. The inspection UI, invalid-value sentinel and callers are authored. [Primary source](https://www.sqlite.org/fileformat.html#page_size)

- **mirrored_gallery_layout**. Pillow's ImageOps.exif_transpose implementation maps EXIF 5 and 7 to diagonal transforms and 6 and 8 to quarter turns. This authored gallery reproduces the effect on layout width. [Primary source](https://github.com/python-pillow/Pillow/blob/10.4.0/src/PIL/ImageOps.py#L688-L701)

- **utf16_editor_offsets**. The Unicode Standard defines scalar values and their UTF-16 encoding. The cursor and two-scalar selection APIs, including their invalid-value handling, are authored. [Primary source](https://www.unicode.org/versions/Unicode16.0.0/core-spec/chapter-3/#G25660)
