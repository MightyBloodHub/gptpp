"""Frozen paired development tasks. Held-out arguments are never prompt inputs."""

from itertools import product
from textwrap import dedent, indent


def _sources(params, python, scalar):
    types = {
        "python": {"int": "int", "bool": "bool"},
        "rust": {"int": "i64", "bool": "bool"},
        "gpp": {"int": "I64", "bool": "Bool"},
    }
    code = {}
    for language, names in types.items():
        args = ", ".join(f"{name}: {names[typ]}" for name, typ in params)
        if language == "python":
            code[language] = f"def solve({args}) -> int:\n" + indent(dedent(python).strip(), "    ") + "\n"
        else:
            result = "I64 !{}" if language == "gpp" else "i64"
            body = dedent(scalar).strip()
            if language == "rust":
                body = body.replace("var ", "let mut ")
            code[language] = f"fn solve({args}) -> {result} {{\n" + indent(body, "    ") + "\n}\n"
    return code


def _expression(scalar):
    return "return " + scalar.replace("/", "//"), "return " + scalar + ";"


def _task(task_id, form, description, params, examples, trials, oracle, reference, starter=None):
    for args, hand_expected in examples:
        if oracle(*args) != hand_expected:
            raise ValueError(f"{task_id} example disagrees with independent oracle")
    public_args = {args for args, _ in examples}
    hidden = [(args, oracle(*args)) for args in dict.fromkeys(trials) if args not in public_args]
    if len(public_args) != 3 or len(hidden) < 15:
        raise ValueError(f"incomplete case coverage for {task_id}")
    task = dict(id=task_id, kind="maintenance" if starter else "synthesis", form=form,
                description=description, params=params, public=examples, heldout=hidden,
                reference=_sources(params, *reference))
    if starter is not None:
        task["starter"] = _sources(params, *starter)
    return task


def _edges(rows, cols):
    # Enumerate neighboring tile pairs, counting each seam once.
    return sum(int(r + 1 < rows) + int(c + 1 < cols)
               for r in range(rows) for c in range(cols))


def _clock(minutes):
    hour, minute = 0, 0
    for _ in range(minutes):
        minute += 1
        if minute == 60:
            minute = 0
            hour = (hour + 1) % 24
    return int(f"{hour:02}{minute:02}")


def _lane(ahead_a, ahead_b, prefer_b):
    # Sort by predicted wait, then by whether this lane is the tie preference.
    return min((ahead_a * 3, prefer_b, 1), (ahead_b * 2, not prefer_b, 2))[2]


def _levels(stock, first, step):
    return max(k for k in range(20) if k * first + k * (k - 1) * step // 2 <= stock)


def _sheet(page):
    sheets = [[1]] + [[front, front + 1] for front in range(2, 101, 2)]
    return next(i for i, pages in enumerate(sheets, 1) if page in pages)


def _scale(raw, offset, gain):
    return sum(raw for _ in range(gain)) - sum(offset for _ in range(gain))


def _latch(temperature, latched, reset):
    # Prohibited reset temperatures and the ordinary latch threshold are independent.
    set_by_heat = temperature >= 60
    reset_accepted = reset and temperature < 85
    return int((latched or set_by_heat) and not reset_accepted)


def _chime(now, deadline, period):
    # Enumerate schedule entries by occurrence number, independent of the clock scan.
    events = [k * period for k in range(51) if k * period % 10 != 0]
    return min((time for time in events if now < time <= deadline), default=-1)


TASKS = [
    _task(
        "tile_seams", "expr",
        "A rectangle contains rows by cols square tiles. Count the unit-length edges shared "
        "by two tiles. Count each shared edge once and exclude the outside border. Both sizes are 1..8.",
        [("rows", "int"), ("cols", "int")],
        [((2, 3), 7), ((1, 4), 3), ((1, 1), 0)],
        product((1, 2, 3, 5, 8), (1, 2, 4, 7, 8)), _edges,
        _expression("(rows - 1) * cols + (cols - 1) * rows"),
    ),
    _task(
        "clock_display", "expr",
        "Return the 24-hour clock reading after minutes elapsed since midnight as the integer "
        "100 * hour + minute. The clock repeats every day. minutes is 0..4319 inclusive.",
        [("minutes", "int")],
        [((37,), 37), ((125,), 205), ((1503,), 103)],
        [(n,) for n in (0, 1, 9, 59, 60, 61, 119, 120, 599, 600, 719, 720, 1380, 1439,
                        1440, 1441, 1499, 2879, 2880, 2940, 4137, 4319)], _clock,
        _expression("(minutes / 60 % 24) * 100 + minutes % 60"),
    ),
    _task(
        "queue_choice", "body",
        "Lane A takes 3 minutes per customer already ahead, lane B takes 2. Return 1 for A "
        "or 2 for B, choosing the shorter wait. On equal waits choose B when prefer_b is true, "
        "otherwise A. Both queue lengths are 0..12 inclusive.",
        [("ahead_a", "int"), ("ahead_b", "int"), ("prefer_b", "bool")],
        [((1, 4, True), 1), ((3, 2, False), 2), ((2, 3, True), 2)],
        [(a, b, prefer) for a, b in ((0, 0), (0, 12), (12, 0), (2, 3), (4, 6), (6, 9),
                                     (8, 12), (7, 10), (7, 11), (1, 1), (12, 12), (3, 5))
         for prefer in (False, True)], _lane,
        ("""
        if ahead_a * 3 == ahead_b * 2:
            return 2 if prefer_b else 1
        return 1 if ahead_a * 3 < ahead_b * 2 else 2
        """, """
        let a = ahead_a * 3;
        let b = ahead_b * 2;
        if a < b || (a == b && !prefer_b) { return 1; }
        return 2;
        """),
    ),
    _task(
        "full_shelves", "body",
        "Fill shelves in order from stock units. The first shelf needs first units and each later "
        "shelf needs step more units than the previous one. Return the number of completely filled "
        "shelves. stock is 0..80, first is 1..6 and step is 1..4 inclusive.",
        [("stock", "int"), ("first", "int"), ("step", "int")],
        [((10, 1, 1), 4), ((12, 3, 2), 2), ((2, 3, 4), 0)],
        [(0, 1, 1), (0, 6, 4), (1, 1, 4), (6, 6, 1), (5, 6, 1), (7, 6, 1),
         (9, 1, 1), (11, 1, 1), (2, 2, 1), (6, 2, 2), (7, 2, 2), (12, 2, 2),
         (11, 2, 2), (17, 3, 4), (18, 3, 4), (21, 3, 4), (22, 3, 4), (45, 1, 1),
         (46, 1, 1), (80, 1, 1), (80, 1, 4), (80, 6, 4)], _levels,
        ("""
        remaining = stock
        size = first
        filled = 0
        while remaining >= size:
            remaining -= size
            size += step
            filled += 1
        return filled
        """, """
        var remaining = stock;
        var size = first;
        var filled = 0;
        while remaining >= size {
            remaining = remaining - size;
            size = size + step;
            filled = filled + 1;
        }
        return filled;
        """),
    ),
    _task(
        "single_sided_cover", "expr",
        "A duplex printer originally put logical pages 1 and 2 on sheet 1, pages 3 and 4 on "
        "sheet 2, and so on. Change it so page 1 is alone on sheet 1, then use both sides "
        "starting with pages 2 and 3 on sheet 2. Return the physical sheet number for page, "
        "numbering both pages and sheets from 1. page is 1..100 inclusive.",
        [("page", "int")],
        [((1,), 1), ((2,), 2), ((5,), 3)],
        [(n,) for n in (3, 4, 6, 7, 8, 9, 10, 11, 12, 13, 17, 18, 36, 37, 50, 51, 97, 98, 99, 100)],
        _sheet, _expression("page / 2 + 1"), _expression("(page + 1) / 2"),
    ),
    _task(
        "sensor_offset_units", "expr",
        "The sensor previously multiplied raw by gain and then subtracted offset. Calibration "
        "now specifies offset in raw sensor units. Subtract offset from raw before applying "
        "gain. Keep signed readings and return the corrected integer. raw is -25..25, "
        "offset is -5..5 and gain is 1..5 inclusive.",
        [("raw", "int"), ("offset", "int"), ("gain", "int")],
        [((7, 2, 3), 15), ((-4, -1, 2), -6), ((9, 0, 4), 36)],
        [(-25, -5, 1), (-25, 5, 5), (-25, 0, 3), (25, 5, 1), (25, -5, 5), (25, 0, 5),
         (0, -5, 1), (0, -5, 2), (0, 5, 4), (0, 0, 3), (3, 3, 2), (-3, -3, 4),
         (2, 5, 1), (2, 5, 2), (-2, -5, 2), (-2, 4, 3), (14, -1, 4), (-14, 1, 4),
         (1, 0, 1), (0, 1, 5)], _scale,
        _expression("(raw - offset) * gain"), _expression("raw * gain - offset"),
    ),
    _task(
        "alarm_reset", "body",
        "The alarm latches at temperature >= 60 or stays on if already latched. Previously reset "
        "always cleared it. Add a critical threshold: at 85 or above the alarm must stay on even "
        "when reset is requested. Below 85 keep the existing behavior including reset priority. "
        "Return 1 for on, 0 for off. temperature is 0..100 inclusive.",
        [("temperature", "int"), ("latched", "bool"), ("reset", "bool")],
        [((85, False, True), 1), ((84, True, True), 0), ((41, True, False), 1)],
        product((0, 59, 60, 61, 84, 85, 86, 100), (False, True), (False, True)),
        _latch,
        ("""
        if temperature >= 85:
            return 1
        if reset:
            return 0
        return int(latched or temperature >= 60)
        """, """
        if temperature >= 85 { return 1; }
        if reset { return 0; }
        if latched || temperature >= 60 { return 1; }
        return 0;
        """),
        ("""
        if reset:
            return 0
        return int(latched or temperature >= 60)
        """, """
        if reset { return 0; }
        if latched || temperature >= 60 { return 1; }
        return 0;
        """),
    ),
    _task(
        "quiet_chime", "body",
        "The next chime is the earliest integer time strictly after now and at or before deadline "
        "that is a multiple of period. Change the schedule to suppress all chimes at multiples of "
        "10. Keep the time bounds and return -1 if no eligible chime remains. now and deadline "
        "are each 0..50 (deadline can precede now), and period is 1..12 inclusive.",
        [("now", "int"), ("deadline", "int"), ("period", "int")],
        [((9, 12, 2), 12), ((9, 10, 5), -1), ((3, 6, 3), 6)],
        [(0, 0, 1), (50, 0, 2), (12, 12, 3), (7, 9, 2), (7, 10, 5), (7, 15, 5),
         (8, 11, 2), (8, 12, 2), (10, 20, 10), (0, 50, 10), (29, 31, 3),
         (29, 33, 3), (44, 50, 5), (45, 50, 5), (1, 50, 12), (47, 48, 12),
         (48, 50, 12), (1, 1, 12), (0, 1, 1), (39, 40, 1), (39, 41, 1),
         (49, 50, 1)], _chime,
        ("""
        for time in range(now + 1, deadline + 1):
            if time % period == 0 and time % 10 != 0:
                return time
        return -1
        """, """
        var time = now + 1;
        while time <= deadline {
            if time % period == 0 && time % 10 != 0 { return time; }
            time = time + 1;
        }
        return -1;
        """),
        ("""
        for time in range(now + 1, deadline + 1):
            if time % period == 0:
                return time
        return -1
        """, """
        var time = now + 1;
        while time <= deadline {
            if time % period == 0 { return time; }
            time = time + 1;
        }
        return -1;
        """),
    ),
]
