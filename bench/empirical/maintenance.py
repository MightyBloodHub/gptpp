"""Fresh scalar maintenance tasks for the paired development experiment."""
from textwrap import dedent, indent


def _source(params, python, brace_body):
    """The Rust and GPT++ functions share imperative bodies and signature order."""
    def signature(types):
        return ", ".join(f"{name}: {types[ty]}" for name, ty in params)

    body = indent(dedent(brace_body).strip(), "    ")
    py_sig = signature({"int": "int", "bool": "bool"})
    rs_sig = signature({"int": "i64", "bool": "bool"})
    gp_sig = signature({"int": "I64", "bool": "Bool"})
    return {
        "python": f"def solve({py_sig}) -> int:\n" + indent(dedent(python).strip(), "    ") + "\n",
        "rust": f"fn solve({rs_sig}) -> i64 {{\n" + body.replace("var ", "let mut ") + "\n}\n",
        "gpp": f"fn solve({gp_sig}) -> I64 !{{}} {{\n" + body + "\n}\n",
    }


def _task(name, description, params, public, heldout, oracle, starter, reference):
    return dict(
        id=f"maintenance_{name}", kind="maintenance", description=description, params=params,
        public=[(args, oracle(*args)) for args in public],
        heldout=[(args, oracle(*args)) for args in heldout],
        starter=_source(params, *starter), reference=_source(params, *reference),
    )


def _bracket():
    params = [("units", "int"), ("member", "bool")]
    py = """
    first = min(units, 8)
    extra = units - first
    charge = 5 * first + 3 * extra
    if member and units > 0:
        charge -= 1
    return charge
    """
    body = """
    var first = units;
    if first > 8 { first = 8; }
    let extra = units - first;
    var charge = 5 * first + 3 * extra;
    if member && units > 0 { charge = charge - 1; }
    return charge;
    """
    # Count rebate milestones rather than dividing and capping in the oracle.
    def price(units, member):
        gross = sum(5 if i <= 8 else 3 for i in range(1, units + 1))
        if member:
            gross -= int(units > 0) + sum(2 for milestone in (11, 14, 17) if units >= milestone)
        return gross

    ref = (py.replace("charge -= 1", "charge -= 1 + 2 * min(extra // 3, 3)"),
           body.replace("charge = charge - 1;", """
        var groups = extra / 3;
        if groups > 3 { groups = 3; }
        charge = charge - 1 - 2 * groups;"""))
    public = [(11, True), (8, False), (15, True)]
    hidden = [(u, m) for u in (0, 1, 7, 9, 10, 12, 13, 14, 16, 17, 18, 23, 30)
              for m in (False, True)]
    return _task("bracket_rebate",
                 "A service charges 5 credits per unit for the first 8 units and 3 per unit thereafter. "
                 "Members keep the existing 1-credit discount on every nonempty purchase. Add a further "
                 "member discount of 2 credits per complete group of 3 units above 8, for at most 3 groups. "
                 "Return the final charge. Keep nonmember pricing and zero purchases unchanged. "
                 "units is 0..30 inclusive.", params, public, hidden, price, (py, body), ref)


def _rotating():
    params = [("size", "int"), ("start", "int"), ("steps", "int"), ("closed", "bool")]
    py = """
    if closed:
        return start
    return (start + steps) % size
    """
    body = """
    if closed { return start; }
    return ((start + steps) % size + size) % size;
    """
    py_ref = """
    position = start
    direction = 1 if steps >= 0 else -1
    for _ in range(abs(steps)):
        position = (position + direction) % size
        if closed and position == 0:
            position = (position + direction) % size
    return position
    """
    body_ref = """
    var pos = start;
    var remaining = steps;
    var direction = 1;
    if steps < 0 { direction = -1; remaining = -steps; }
    while remaining > 0 {
        pos = (pos + size + direction) % size;
        if closed && pos == 0 { pos = (pos + size + direction) % size; }
        remaining = remaining - 1;
    }
    return pos;
    """
    def ring(size, start, steps, closed):
        if not steps:
            return start
        ring_slots = list(range(int(closed), size))
        if start in ring_slots:
            index = ring_slots.index(start)
        else:
            # Starting in the closed slot is legal. First move enters the ring at the near end.
            index = -1 if steps > 0 else 0
        return ring_slots[(index + steps) % len(ring_slots)]

    public = [(5, 4, 1, True), (5, 0, -1, True), (4, 3, 2, False)]
    hidden = [(2, 0, 0, True), (2, 0, 1, True), (2, 1, -12, True), (2, 1, 7, False),
              (3, 1, -1, True), (3, 2, -3, True), (3, 0, 2, True), (3, 1, 0, True),
              (4, 3, 8, True), (6, 1, -7, True), (6, 5, 12, True), (6, 0, -12, True),
              (8, 4, -5, False), (9, 8, 12, False), (9, 0, -12, False), (12, 11, 0, False),
              (12, 1, -12, True), (12, 0, -1, False), (7, 2, -1, True), (10, 9, 3, True)]
    return _task("rotating_index",
                 "A dial has slots 0 through size-1. Positive steps move clockwise toward increasing "
                 "indices and negative steps move the other way, wrapping at both ends. Change closed "
                 "mode: movement now works, but slot 0 must be skipped without consuming a step, in "
                 "either direction. Starting at 0 is legal. Zero steps always leave the start unchanged. "
                 "Retain open mode behavior. Return the ending slot. size is 2..12, start is 0..size-1, "
                 "steps is -12..12, all inclusive.", params, public, hidden, ring, (py, body), (py_ref, body_ref))


def _quota():
    params = [("total", "int"), ("teams", "int"), ("team", "int"), ("round_id", "int")]
    py = """
    rank = team if round_id % 2 == 0 else teams - 1 - team
    return total // teams + int(rank < total % teams)
    """
    body = """
    var rank = team;
    if round_id % 2 != 0 { rank = teams - 1 - team; }
    let base = total / teams;
    if rank < total % teams { return base + 1; }
    return base;
    """
    py_ref = py.replace("team if round_id % 2 == 0 else teams - 1 - team", "(team - round_id) % teams")
    body_ref = body.replace("var rank = team;\n    if round_id % 2 != 0 { rank = teams - 1 - team; }",
                            "let rank = (team + teams - round_id % teams) % teams;")

    def allocation(total, teams, team, round_id):
        return sum((round_id + i) % teams == team for i in range(total))

    public = [(8, 3, 0, 1), (8, 3, 1, 1), (12, 4, 3, 6)]
    hidden = [(t, n, i, r) for t, n, r in
              [(0, 1, 11), (0, 4, 2), (7, 1, 0), (4, 3, 2), (2, 6, 11), (8, 5, 8), (40, 7, 15), (13, 8, 0)]
              for i in range(n)]
    return _task("split_quota",
                 "Split total items evenly among teams numbered 0 through teams-1. Each team still gets "
                 "the integer base share. Change the extra-item rule: start at team round_id modulo teams "
                 "and give one extra to each successive team, wrapping to zero, until the leftovers run "
                 "out. Return the allocation for team. Preserve divisible totals and the single-team case. "
                 "total is 0..40, teams 1..8, team 0..teams-1 and round_id 0..15, all inclusive.",
                 params, public, hidden, allocation, (py, body), (py_ref, body_ref))


def _streak():
    params = [("mask", "int"), ("width", "int")]
    py = """
    value = mask
    run = best = 0
    for i in range(width):
        run = run + 1 if value % 2 else 0
        best = max(best, run)
        value //= 2
    return best
    """
    body = """
    var value = mask;
    var run = 0;
    var best = 0;
    var i = 0;
    while i < width {
        if value % 2 == 1 { run = run + 1; } else { run = 0; }
        if run > best { best = run; }
        value = value / 2;
        i = i + 1;
    }
    return best;
    """
    py_ref = py.replace("range(width):", "range(2 * width):\n        if i == width:\n            value = mask").replace(
        "return best", "return min(best, width)")
    body_ref = body.replace("i < width {", "i < width * 2 {\n        if i == width { value = mask; }").replace(
        "return best;", "if best > width { return width; }\n    return best;")

    def longest(mask, width):
        return max(k for k in range(width + 1)
                   if any(all(mask & (1 << ((i + offset) % width)) for offset in range(k))
                          for i in range(width)))

    public = [(9, 4), (15, 4), (6, 5)]
    hidden = [(0, 1), (1, 1), (2, 1), (0, 3), (1, 4), (5, 3), (7, 3), (8, 3), (17, 4),
              (19, 5), (25, 5), (29, 5), (31, 5), (43, 6), (53, 6), (112, 7),
              (127, 7), (130, 7), (257, 9), (385, 9), (511, 9), (1023, 3)]
    return _task("marker_streak",
                 "The low width binary digits of mask mark occupied slots (1 = occupied). Return the "
                 "longest consecutive run of occupied slots. Change the layout from a line to a ring: "
                 "the last slot now touches the first. Each slot can contribute at most once to a run. "
                 "Continue ignoring higher bits and return zero for an empty ring. mask is 0..1023 "
                 "and width is 1..9, inclusive.", params, public, hidden, longest, (py, body), (py_ref, body_ref))


def _rounding():
    params = [("total", "int"), ("count", "int")]
    py = """
    magnitude = abs(total)
    whole, rem = divmod(magnitude, count)
    if 2 * rem >= count:
        whole += 1
    return -whole if total < 0 else whole
    """
    body = """
    var magnitude = total;
    if total < 0 { magnitude = -total; }
    var whole = magnitude / count;
    let twice = (magnitude % count) * 2;
    if twice >= count { whole = whole + 1; }
    if total < 0 { return -whole; }
    return whole;
    """
    py_ref = py.replace("2 * rem >= count", "2 * rem > count or (2 * rem == count and whole % 2 == 1)")
    body_ref = body.replace("twice >= count", "twice > count || (twice == count && whole % 2 == 1)")

    def nearest(total, count):
        return min(range(-90, 91), key=lambda n: (abs(total - n * count), n % 2))

    public = [(5, 2), (-7, 2), (11, 3)]
    hidden = [(a, b) for a in (-15, -9, -5, -3, -1, 0, 1, 3, 7, 9, 15) for b in (2, 6)]
    hidden += [(-90, 1), (90, 8), (-23, 7), (7, 4), (10, 4), (18, 4), (-18, 4), (45, 5)]
    return _task("sample_rounding",
                 "Return the arithmetic mean total/count rounded to the nearest integer. Replace the "
                 "old ties-away-from-zero rule: when equally close to two integers, choose the even "
                 "integer. Preserve exact quotients and every non-tied nearest result, including for "
                 "negative totals. total is -90..90 and count is 1..8, inclusive.",
                 params, public, hidden, nearest, (py, body), (py_ref, body_ref))


def _reserve():
    params = [("initial", "int"), ("load", "int"), ("days", "int")]
    py = """
    level = initial
    for day in range(days):
        level = min(12, level + 3)
        if level < load:
            return day
        level -= load
    return days
    """
    body = """
    var level = initial;
    var day = 0;
    while day < days {
        level = level + 3;
        if level > 12 { level = 12; }
        if level < load { return day; }
        level = level - load;
        day = day + 1;
    }
    return days;
    """
    py_ref = py.replace("if level < load:", "reserve = 2 if day + 1 < days else 0\n        if level - load < reserve:")
    body_ref = body.replace("if level < load", "var reserve = 0;\n        if day + 1 < days { reserve = 2; }\n        if level - load < reserve")

    def completed(initial, load, days):
        first_balance = min(initial + 3, 12) - load
        for day in range(1, days + 1):
            ending_balance = min(12 - load, first_balance + (day - 1) * (3 - load))
            if ending_balance < (2 if day < days else 0):
                return day - 1
        return days

    public = [(0, 2, 3), (0, 3, 1), (8, 5, 4)]
    hidden = [(0, 8, 0), (12, 0, 0), (0, 4, 1), (0, 1, 9), (0, 3, 2), (1, 3, 4),
              (2, 3, 4), (1, 4, 1), (6, 4, 7), (6, 4, 8), (12, 8, 2), (12, 8, 3),
              (12, 7, 2), (12, 7, 3), (12, 5, 3), (12, 5, 4), (11, 3, 9),
              (10, 0, 9), (4, 2, 7), (4, 6, 2), (5, 6, 2), (9, 5, 7)]
    return _task("reserve_floor",
                 "A tank starts at initial. Each morning add 3 units, capping the level at 12, "
                 "then attempt to supply exactly load units. Change the rule: each day except the "
                 "last requested day must leave at least 2 units after supplying the load. On the "
                 "last day a balance of zero is allowed. Stop at the first failed day and return "
                 "the number of fully supplied days. Preserve the cap, replenishment order and "
                 "zero-day behavior. initial is 0..12, load 0..8 and days 0..9, inclusive.",
                 params, public, hidden, completed, (py, body), (py_ref, body_ref))


TASKS = [_bracket(), _rotating(), _quota(), _streak(), _rounding(), _reserve()]
