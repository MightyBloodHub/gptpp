"""Frozen replication corpus. Examples are public; all other cases stay with the scorer."""

# Share the corpus schema and language wrappers with the first paired study.
if __package__:
    from .tasks import _expression, _task
else:
    from tasks import _expression, _task


def _fade(start, end, tick):
    # Average eight contributing samples, replacing one at each transition.
    samples = [end] * tick + [start] * (8 - tick)
    return sum(samples) // len(samples)


def _station(left, right, position):
    return min((left, right), key=lambda s: (abs(s - position), s))


def _check_digit(payload):
    string = f"{payload:05d}"
    digits = [int(s) * weight for s, weight in zip(string, (2, 1, 2, 1, 2))]
    checksum = sum(int(c) for n in digits for c in str(n))
    return next(n for n in range(10) if (checksum + n) % 10 == 0)


def _kits(bolts, clips):
    divisors = [n for n in range(1, max(bolts, clips) + 1) if bolts % n == 0 and clips % n == 0]
    return (bolts + clips) // max(divisors)


def _color(red, green, blue):
    bits = f"{blue:08b}"[:5] + f"{green:08b}"[:6] + f"{red:08b}"[:5]
    return int(bits, 2)


def _slew(current, target, rate):
    direction, steps = (1, rate) if current < target else (-1, 2 * rate)
    for _ in range(steps):
        if current != target:
            current += direction
    return current


def _loan(balance, payment, months):
    for _ in range(months):
        paid = min(balance, payment)
        left = balance - paid
        fee = sum(1 for _ in range(10, left + 1, 10))
        balance = left + fee
    return balance


def _race(seconds, misses, finished):
    # Officials publish a penalty table indexed by the number of missed gates.
    table = (0, 5, 10, 35)
    if finished and misses < len(table):
        return seconds + table[misses]
    return -1


TASKS = [
    _task(
        "fade_level", "expr",
        "A lamp fades linearly from start at tick 0 to end at tick 8. Return the value at "
        "tick, rounded down to an integer. start and end are in 0..100 and tick in 0..8 "
        "inclusive. The fade may brighten or dim.",
        [("start", "int"), ("end", "int"), ("tick", "int")],
        [((0, 100, 2), 25), ((19, 5, 3), 13), ((7, 90, 8), 90)],
        [(s, e, t) for s, e in ((0, 99), (100, 0), (1, 2), (7, 7), (63, 19))
         for t in (0, 1, 4, 7, 8)], _fade,
        _expression("((8 - tick) * start + tick * end) / 8"),
    ),
    _task(
        "nearest_station", "expr",
        "Two stations lie on a straight line at coordinates left and right. Return the "
        "coordinate of the station nearest to position. At an exact tie return left. All "
        "coordinates are integers in -40..40 inclusive, with left <= right.",
        [("left", "int"), ("right", "int"), ("position", "int")],
        [((-8, 4, -2), -8), ((1, 10, 6), 10), ((-6, -4, -10), -6)],
        [(lo, hi, x) for lo, hi in ((-40, 40), (-21, -7), (7, 7), (1, 6), (-4, 9))
         for x in (-40, lo, (lo + hi) // 2, (lo + hi) // 2 + 1, hi, 40)],
        _station,
        ("return left if position * 2 <= left + right else right",
         "return if position * 2 <= left + right { left } else { right };"),
    ),
    _task(
        "parcel_check_digit", "body",
        "Compute a decimal check digit for a five-digit parcel payload (pad with leading "
        "zeros). From right to left double the first, third and fifth payload digits. "
        "For each doubled value at least 10 subtract 9. Sum all five resulting values. "
        "Return the digit 0..9 that makes the sum plus that digit a multiple of 10. "
        "payload is 0..99999 inclusive.",
        [("payload", "int")],
        [((12345,), 5), ((59,), 6), ((0,), 0)],
        [(n,) for n in (1, 4, 5, 9, 10, 19, 90, 99, 100, 101, 105, 111, 123, 909,
                        9876, 10000, 50001, 31415, 45454, 55555, 90909, 99999)], _check_digit,
        ("""
        value = payload
        total = 0
        for i in range(5):
            digit = value % 10
            if i % 2 == 0:
                digit *= 2
                if digit >= 10:
                    digit -= 9
            total += digit
            value //= 10
        return (10 - total % 10) % 10
        """, """
        var value = payload;
        var total = 0;
        var i = 0;
        while i < 5 {
            var digit = value % 10;
            if i % 2 == 0 {
                digit = digit * 2;
                if digit >= 10 { digit = digit - 9; }
            }
            total = total + digit;
            value = value / 10;
            i = i + 1;
        }
        return (10 - total % 10) % 10;
        """),
    ),
    _task(
        "identical_repair_kits", "body",
        "Distribute all bolts and clips into the largest possible number of identical, "
        "nonempty repair kits. Every kit must have the same number of bolts and the same "
        "number of clips. Return the total number of parts in one kit. Both counts are "
        "0..40 inclusive and at least one count is positive.",
        [("bolts", "int"), ("clips", "int")],
        [((12, 8), 5), ((9, 0), 1), ((6, 5), 11)],
        [(0, 1), (0, 40), (1, 0), (40, 0), (1, 1), (4, 4), (40, 40), (1, 39),
         (2, 4), (4, 2), (9, 6), (6, 9), (14, 21), (24, 16), (24, 18), (35, 14),
         (34, 21), (39, 40), (36, 24), (32, 8), (25, 15), (40, 36)], _kits,
        ("""
        a, b = bolts, clips
        while b:
            a, b = b, a % b
        return (bolts + clips) // a
        """, """
        var a = bolts;
        var b = clips;
        while b != 0 {
            let rest = a % b;
            a = b;
            b = rest;
        }
        return (bolts + clips) / a;
        """),
    ),
    _task(
        "panel_color_order", "expr",
        "The panel packs three 8-bit color channels into a 16-bit integer. Keep the top 5 "
        "bits of red, top 6 of green and top 5 of blue. Change the old red-green-blue "
        "field order: the new panel expects blue in the most significant 5 bits, green "
        "in the middle 6 bits and red in the least significant 5 bits. Inputs are 0..255.",
        [("red", "int"), ("green", "int"), ("blue", "int")],
        [((255, 0, 0), 31), ((0, 255, 0), 2016), ((32, 128, 248), 64516)],
        [(0, 0, 0), (255, 255, 255), (0, 0, 255), (0, 1, 0), (7, 3, 7),
         (7, 4, 8), (8, 3, 7), (8, 4, 8), (15, 7, 0), (0, 8, 16), (16, 0, 255),
         (248, 252, 248), (127, 128, 129), (129, 128, 127), (53, 64, 57), (56, 71, 60),
         (255, 0, 7), (7, 255, 255), (188, 123, 3), (12, 37, 199), (17, 19, 23)],
        _color,
        _expression("(blue / 8) * 2048 + (green / 4) * 32 + red / 8"),
        _expression("(red / 8) * 2048 + (green / 4) * 32 + blue / 8"),
    ),
    _task(
        "actuator_downrate", "expr",
        "One control cycle moves current toward target by at most rate units without "
        "overshooting, in either direction. Change downward movement to allow up to "
        "twice rate per cycle. Keep upward movement and the no-overshoot rule. Return "
        "the new position. current and target are 0..100 and rate is 1..12 inclusive.",
        [("current", "int"), ("target", "int"), ("rate", "int")],
        [((30, 15, 4), 22), ((30, 26, 4), 26), ((30, 40, 4), 34)],
        [(0, 0, 1), (0, 1, 1), (100, 100, 12), (100, 0, 12), (0, 100, 12),
         (18, 16, 1), (18, 17, 1), (18, 18, 1), (18, 19, 1), (18, 20, 1),
         (40, 30, 5), (40, 31, 5), (40, 29, 5), (40, 35, 5), (40, 34, 5),
         (12, 0, 12), (13, 0, 12), (24, 0, 12), (25, 0, 12), (10, 20, 11), (55, 45, 3)],
        _slew,
        ("return min(current + rate, max(target, current - 2 * rate))",
         "return if target > current + rate { current + rate } else { "
         "if target < current - 2 * rate { current - 2 * rate } else { target } };"),
        ("return min(current + rate, max(target, current - rate))",
         "return if target > current + rate { current + rate } else { "
         "if target < current - rate { current - rate } else { target } };"),
    ),
    _task(
        "interest_after_payment", "body",
        "Simulate months of a loan with nonnegative integer balances. Each month used to "
        "add floor(10% of balance) as interest before making a payment. Change the order: "
        "first deduct payment, clamping the balance to zero; then add floor(10% of that "
        "remaining balance). Return the ending balance. balance is 0..120, payment is "
        "0..20 and months is 0..8 inclusive.",
        [("balance", "int"), ("payment", "int"), ("months", "int")],
        [((100, 10, 1), 99), ((18, 20, 1), 0), ((10, 0, 2), 12)],
        [(0, 0, 8), (0, 20, 8), (19, 20, 0), (120, 20, 0), (120, 20, 1),
         (120, 20, 8), (109, 20, 3), (10, 1, 1), (11, 1, 1), (19, 9, 1),
         (20, 9, 1), (20, 10, 2), (20, 20, 1), (19, 20, 1), (120, 0, 8),
         (50, 5, 8), (49, 5, 8), (34, 7, 4), (8, 1, 6), (7, 1, 8), (80, 13, 4)],
        _loan,
        ("""
        remaining = balance
        for _ in range(months):
            remaining = max(0, remaining - payment)
            remaining += remaining // 10
        return remaining
        """, """
        var remaining = balance;
        var month = 0;
        while month < months {
            remaining = remaining - payment;
            if remaining < 0 { remaining = 0; }
            remaining = remaining + remaining / 10;
            month = month + 1;
        }
        return remaining;
        """),
        ("""
        remaining = balance
        for _ in range(months):
            remaining += remaining // 10
            remaining = max(0, remaining - payment)
        return remaining
        """, """
        var remaining = balance;
        var month = 0;
        while month < months {
            remaining = remaining + remaining / 10;
            remaining = remaining - payment;
            if remaining < 0 { remaining = 0; }
            month = month + 1;
        }
        return remaining;
        """),
    ),
    _task(
        "slalom_penalty", "body",
        "Return official slalom time in seconds or -1 for a disqualification. Under "
        "the old rules a nonfinisher or racer with at least 3 missed gates was "
        "disqualified; other finishers added 5 seconds per missed gate. Now allow "
        "finishers with exactly 3 misses to score their time plus the usual 15 seconds "
        "and an additional 20 seconds. Keep all other outcomes. seconds is 0..300 "
        "and misses is 0..6 inclusive.",
        [("seconds", "int"), ("misses", "int"), ("finished", "bool")],
        [((84, 3, True), 119), ((84, 3, False), -1), ((90, 2, True), 100)],
        [(s, m, f) for s in (0, 49, 198, 300) for m in (0, 1, 2, 3, 4, 6)
         for f in (False, True)], _race,
        ("""
        if not finished or misses >= 4:
            return -1
        if misses == 3:
            return seconds + 35
        return seconds + 5 * misses
        """, """
        if !finished || misses >= 4 { return -1; }
        if misses == 3 { return seconds + 35; }
        return seconds + 5 * misses;
        """),
        ("""
        if not finished or misses >= 3:
            return -1
        return seconds + 5 * misses
        """, """
        if !finished || misses >= 3 { return -1; }
        return seconds + 5 * misses;
        """),
    ),
]
