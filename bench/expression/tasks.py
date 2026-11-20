"""Pinned single-expression changes with two upstream use sites per project.

Each site string identifies exactly one existing expression in the target body.
The paired fixes and withheld cases are scorer data. See sources.md for scope.
"""

from datetime import date
from fractions import Fraction

from bench.policy.fresh import _task


def _cases(oracle, groups):
    return [(index, args, oracle[index](*args)) for index, args in groups]


def _fixture(*, name, target, params, description, commit, provenance, starter,
             site, fix, callers, oracle, public, heldout):
    reference = []
    for body, before, after in zip(starter, site, fix):
        if body.count(before) != 1:
            raise ValueError(f"{name}: ambiguous expression {before!r}")
        reference.append(body.replace(before, f"({after})", 1))
    task = _task(name, "body", target, params, description, commit, provenance,
                 starter, reference, callers, _cases(oracle, public), _cases(oracle, heldout))
    for field, values in (("site", site), ("fix", fix)):
        python, braced = values
        task[field] = {"python": python, "gpp": braced, "rust": braced}
    return task


def _redis():
    def stamp(clock, idle, multiplier):
        # Walk backward by one tick at a time under the pinned Redis convention.
        result = clock
        for _ in range(idle * multiplier // 1000):
            result = result - 1 if result else 16777214
        return result

    return _fixture(
        name="redis_lru_timestamp", target="access_stamp", params="clock idle multiplier",
        description="Recover the stored 24-bit last-access timestamp from the current clock and an idle "
                    "duration. Convert the duration to whole one-second ticks, rounding down. If the "
                    "timestamp crosses zero, Redis idle-time decoding measures elapsed ticks as "
                    "clock + (16777215 - stored). Recover the stamp consistent with that elapsed time. "
                    "Clock is 0..16777215. Idle duration is 0..10000 ticks, supplied in seconds "
                    "(multiplier 1000) or milliseconds (multiplier 1).",
        commit="https://github.com/redis/redis/commit/b458b2999b749950c5ea9468cfa5ab74782848c3",
        provenance="LRU arm of objectSetLRUOrLFU, including the pinned maximum-value wrap convention.",
        starter=("""limit = 16777215
age = idle * multiplier // 1000
absolute = clock - age
if absolute < 0:
    return (clock + limit // 2) % limit
return absolute""",
                 """let limit = 16777215;
let age = idle * multiplier / 1000;
let absolute = clock - age;
if absolute < 0 { return (clock + limit / 2) % limit; }
return absolute;"""),
        site=("(clock + limit // 2) % limit", "(clock + limit / 2) % limit"),
        fix=("absolute + limit", "absolute + limit"),
        callers=[
            ("loaded_stamp", "clock seconds", "return access_stamp(clock, seconds, 1000)",
             "return access_stamp(clock, seconds, 1000);"),
            ("module_stamp", "clock millis", "return access_stamp(clock, millis, 1)",
             "return access_stamp(clock, millis, 1);"),
        ],
        oracle=(stamp, lambda c, s: stamp(c, s, 1000), lambda c, m: stamp(c, m, 1)),
        public=[(1, (10, 1000)), (0, (100, 99, 1000)), (2, (3, 3001))],
        heldout=[(0, (0, 1, 1000)), (0, (0, 0, 1000)), (0, (16777215, 0, 1)),
                 (0, (0, 999, 1)), (0, (1, 2000, 1)), (0, (43, 9700, 1000)),
                 (1, (15, 16)), (1, (19, 19)), (1, (41, 40)), (1, (0, 10000)),
                 (2, (4, 4999)), (2, (4, 5000)), (2, (0, 1501)), (2, (23, 1000))],
    )


def _fastled():
    def scale(level, fraction, fixed_mode):
        step = Fraction(fraction + int(fixed_mode), 256)
        return int(level * step)

    def interpolate(start, end, fraction, mode):
        distance = scale(abs(start - end), fraction, mode)
        return start + distance if end >= start else start - distance

    return _fixture(
        name="fastled_fixed_scale", target="scale_channel", params="level fraction ?fixed_mode",
        description="Implement the fixed 8-bit fractional scaling option while retaining legacy mode. "
                    "Legacy mode uses fraction/256. Fixed mode assigns fraction 0 to a weight of 1/256 "
                    "and fraction 255 to full weight, with 256 equally spaced weights. Truncate the "
                    "scaled level downward once. Level and fraction are integers 0..255.",
        commit="https://github.com/FastLED/FastLED/commit/fee800a12e0ccde471379e8e4bd613d13fe1526b",
        provenance="FastLED scale8 C implementation with the compile-time fixed-mode switch expressed as a flag.",
        starter=("product = level * fraction\nreturn product // 256",
                 "let product = level * fraction;\nreturn product / 256;"),
        site=("level * fraction", "level * fraction"),
        fix=("level * (fraction + (1 if fixed_mode else 0))",
             "level * (fraction + (if fixed_mode { 1 } else { 0 }))"),
        callers=[
            ("interpolate_byte", "start end fraction ?fixed_mode",
             """if end > start:
    return start + scale_channel(end - start, fraction, fixed_mode)
return start - scale_channel(start - end, fraction, fixed_mode)""",
             """if end > start { return start + scale_channel(end - start, fraction, fixed_mode); }
return start - scale_channel(start - end, fraction, fixed_mode);"""),
            ("map_byte", "value low high ?fixed_mode",
             "return low + scale_channel(value, high - low, fixed_mode)",
             "return low + scale_channel(value, high - low, fixed_mode);"),
        ],
        oracle=(scale, interpolate, lambda value, low, high, mode: low + scale(value, high - low, mode)),
        public=[(1, (15, 200, 255, True)), (0, (128, 127, False)), (2, (0, 20, 180, True))],
        heldout=[(0, (255, 254, True)), (0, (128, 1, True)), (0, (255, 0, True)),
                 (0, (1, 255, True)), (0, (64, 19, False)), (0, (255, 255, False)),
                 (1, (201, 1, 255, True)), (1, (0, 128, 1, True)), (1, (5, 5, 255, True)),
                 (1, (200, 3, 19, False)), (2, (128, 1, 128, True)), (2, (255, 0, 255, True)),
                 (2, (4, 5, 5, True)), (2, (175, 5, 200, False))],
    )


DAY = 86400
SPRING, AUTUMN = 70 * DAY, 310 * DAY


def _go():
    def boundary(year, elapsed):
        next_year = (date(year + 1, 1, 1) - date(year, 1, 1)).days * DAY
        return next(bound for bound in (SPRING, AUTUMN, next_year) if elapsed < bound)

    def retry(year, elapsed, offset):
        start = max(b for b in (0, SPRING, AUTUMN) if b <= elapsed)
        return int(offset != 0 and not start <= elapsed - offset < boundary(year, elapsed))

    return _fixture(
        name="go_footer_year_end", target="period_end", params="year elapsed",
        description="Return the exclusive end of the current time-zone period in seconds since January 1. "
                    "Keep the two existing transition instants. After the autumn transition the period "
                    "ends at the next Gregorian January 1, including in leap years. Integer years are "
                    "1600..2400 and elapsed is a valid second within the supplied year.",
        commit="https://github.com/golang/go/commit/4f25c33e83df34f27e939f40109c27831e508b09",
        provenance="Northern-hemisphere tzset interval ends, observed through Time.ZoneBounds and Date's offset retry.",
        starter=("""if elapsed < 6048000:
    return 6048000
if elapsed < 26784000:
    return 26784000
return 365 * 86400""",
                 """if elapsed < 6048000 { return 6048000; }
if elapsed < 26784000 { return 26784000; }
return 365 * 86400;"""),
        site=("365", "365"),
        fix=("366 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 365",
             "if year % 4 == 0 && (year % 100 != 0 || year % 400 == 0) { 366 } else { 365 }"),
        callers=[
            ("zone_bounds_end", "year elapsed january_unix", "return january_unix + period_end(year, elapsed)",
             "return january_unix + period_end(year, elapsed);"),
            ("date_rechecks", "year elapsed offset",
             """start = 26784000 if elapsed >= 26784000 else (6048000 if elapsed >= 6048000 else 0)
utc = elapsed - offset
return int(offset != 0 and (utc < start or utc >= period_end(year, elapsed)))""",
             """let start = if elapsed >= 26784000 { 26784000 } else { if elapsed >= 6048000 { 6048000 } else { 0 } };
let utc = elapsed - offset;
return if offset != 0 && (utc < start || utc >= period_end(year, elapsed)) { 1 } else { 0 };"""),
        ],
        oracle=(boundary, lambda y, s, jan: jan + boundary(y, s), retry),
        public=[(1, (2040, 365 * DAY, 2208988800)), (0, (2100, AUTUMN)), (2, (2040, SPRING, 3600))],
        heldout=[(0, (1900, AUTUMN + 9)), (0, (2000, 366 * DAY - 1)), (0, (2400, AUTUMN)),
                 (0, (2028, SPRING - 1)), (0, (2024, AUTUMN - 1)), (0, (2023, 365 * DAY - 1)),
                 (1, (1600, AUTUMN, -11676096000)), (1, (2024, 365 * DAY + 10, 1704067200)),
                 (1, (2001, SPRING, 978307200)), (1, (2000, 0, 946684800)),
                 (2, (2000, 365 * DAY + 2, -3600)), (2, (2024, 365 * DAY - 1, -3600)),
                 (2, (1900, 365 * DAY - 1, -3600)), (2, (2024, AUTUMN + 3600, 3600)),
                 (2, (2000, 366 * DAY - 1, 0))],
    )


TASKS = [_redis(), _fastled(), _go()]
