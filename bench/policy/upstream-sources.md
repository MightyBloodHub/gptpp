# Upstream transfer fixtures

These three fixtures reproduce maintenance changes from Linux, Moment.js and Godot. Each keeps a bounded scalar input domain and two identifiable upstream uses of the changed result. The starter, reference, adapters and 61 public and withheld judgments were fixed before collecting transfer completions. The fixture author selected the changes without reading the scored v7 outputs. Each was chosen for scalar portability. This is a test of transfer to historical changes, with possible model pretraining exposure.

## Linux signed nearest-integer division

A kernel hardware-monitoring maintainer reported that dividing −2 by 2 with `DIV_ROUND_CLOSEST` yielded 0. The change handles negative dividends for a positive divisor and rounds ties away from zero. The fixture takes bounded signed inputs, and its starter reproduces C integer division toward zero even on the typed Python surface. Arithmetic stays well within the original intermediate range. [Change and report](https://github.com/torvalds/linux/commit/b6d86d3d6d6e4c9b588d81615c81b5a8292b62ed) · [Previous macro](https://github.com/torvalds/linux/blob/4cbe5a555fa58a79b6ecbb6c531b8bab0650778d/include/linux/kernel.h#L85-L90) · [Fixed macro](https://github.com/torvalds/linux/blob/b6d86d3d6d6e4c9b588d81615c81b5a8292b62ed/include/linux/kernel.h#L86-L98)

- `temp_offset_register` extracts the register value computed by the Winbond driver's `store_temp_offset`. It converts millidegrees to degrees, clamped to −128..127. [Offset calculation and write](https://github.com/torvalds/linux/blob/b6d86d3d6d6e4c9b588d81615c81b5a8292b62ed/drivers/hwmon/w83627ehf.c#L1248-L1266)
- `hysteresis_register` extracts the EMC1403 driver's `store_hyst` calculation after a successful sensor read. It subtracts the sensor value in millidegrees and returns the resulting byte or the driver's range error, −34. The adapters expose the value passed to the writer. Parsing, device I/O and locking are outside the extraction. [Hysteresis calculation and write](https://github.com/torvalds/linux/blob/b6d86d3d6d6e4c9b588d81615c81b5a8292b62ed/drivers/hwmon/emc1403.c#L146-L175)

## Moment.js February in year zero

Moment rejected February 29 in astronomical year zero through JavaScript's `Date.UTC` remapping of years 0..99. The merged correction computes the Gregorian month length using the supplied year and a normalized zero-indexed month. The scalar versions handle integer years −400..2400 and month overflow of at most one year. The pre-change implementation explicitly encodes the original ECMAScript year remapping. The domain excludes invalid dates represented by NaN. [Issue #3358](https://github.com/moment/moment/issues/3358) · [Merged correction](https://github.com/moment/moment/commit/f5953bdf32bca2b48581f6058469008aed1de027) · [Previous function](https://github.com/moment/moment/blob/71c41b12344b31feef467d5a7225376e442226ee/src/lib/units/month.js#L17-L19) · [Fixed function](https://github.com/moment/moment/blob/f5953bdf32bca2b48581f6058469008aed1de027/src/lib/units/month.js#L19-L26)

- `set_month_day` returns the chosen day of month from the numeric path in `setMonth`. It preserves the original clamp before the date setter. The inputs substitute a valid Moment object's year, desired month and current day. [Day selection](https://github.com/moment/moment/blob/f5953bdf32bca2b48581f6058469008aed1de027/src/lib/units/month.js#L178-L201)
- `check_overflow` returns Moment's parsing overflow code for an invalid month (1), an invalid day (2) or a valid date (−1). Time fields and parsing flags are fixed to valid values, preserving the original check order. [Parse overflow selection](https://github.com/moment/moment/blob/f5953bdf32bca2b48581f6058469008aed1de027/src/lib/create/check-overflow.js#L5-L17)

## Godot integer rectangle intersection

Godot's correction excludes rectangles that share only a border from `Rect2i::intersects`. The fixture covers its intersection change for positive-sized pixel rectangles. The same commit separately changed `encloses`. Translation places the first rectangle at the origin, and an integer 0 or 1 represents the predicate result. Zero and negative sizes are outside this domain. [Change](https://github.com/godotengine/godot/commit/23a4fe5b27c191eae1dde05aa522463e67b0766f) · [Previous predicate](https://github.com/godotengine/godot/blob/d7822cbf2136b5dcff899b498c80c139b7701c9e/core/math/rect2.h#L379-L399) · [Fixed predicate](https://github.com/godotengine/godot/blob/23a4fe5b27c191eae1dde05aa522463e67b0766f/core/math/rect2.h#L379-L399)

- `intersection_span` extracts the size calculation from the direct caller `Rect2i::intersection`. The local return value is width plus height. It is zero precisely when both dimensions are zero. In the old implementation, an edge contact could produce width zero and positive height, making this distinction observable to a caller. [Clipping calculation](https://github.com/godotengine/godot/blob/23a4fe5b27c191eae1dde05aa522463e67b0766f/core/math/rect2.h#L416-L433)
- `copy_to_back_buffer` preserves the renderer's transitive call and its decision to schedule a copy when the clipped size differs from the zero vector. Its result records whether the renderer would dispatch the copy on a valid render target, without allocating textures or calling the GPU. The positive-size domain selects the explicit-region branch. [Render copy gate](https://github.com/godotengine/godot/blob/23a4fe5b27c191eae1dde05aa522463e67b0766f/servers/rendering/renderer_rd/renderer_storage_rd.cpp#L8090-L8109)

## Validation

The fixtures derive expected outputs independently using Decimal nearest rounding with ties away from zero, Python's Gregorian `calendar.monthrange`, and intersections of enumerated pixel sets. There are nine public examples and 52 withheld examples. The existing sandbox preflight passed all 183 reference judgments across GPT++, typed Python and Rust. Each starter failed a change example while preserving observations through both callers.

An additional local differential check executed the actual pinned C macro, JavaScript function and C++ method from both revisions. Clang compiled the macro and rectangle method with minimal scalar wrappers. Node executed the original JavaScript functions and dependencies. For each revision the locally translated Python target agreed on 1,500 signed divisions drawn with seed 195188, 4,176 normalized calendar inputs, and 720 rectangle placements covering edge and corner contacts. The fixed revisions also agreed with the independent oracles on all 6,396 inputs. These checks cover the extracted scalar leaf. They do not exercise hardware, the full JavaScript date engine's input domain, or the renderer.

To repeat the cross-language preflight from the repository root on the configured macOS benchmark worker:

```sh
target/empirical-venv/bin/python -B - <<'PY'
from bench.policy.run_policy import ROOT, Tools, maintenance
from bench.policy.upstream import TASKS
print(maintenance.calibrate(Tools(ROOT, ROOT / "target/debug/gpp"), TASKS))
PY
```
