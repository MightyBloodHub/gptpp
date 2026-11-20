"""Fresh public-development synthesis tasks for the paired scalar benchmark."""

from random import Random
from textwrap import dedent


def _task(task_id, description, params, examples, edges, domains, oracle, sources):
    # Vary the draw by task. Lists preserve the chosen case order across processes.
    rng = Random(task_id)
    seen = set(examples)
    heldout = []
    for args in edges:
        if args not in seen:
            heldout.append(args)
            seen.add(args)
    while len(heldout) < 32:
        args = tuple(rng.choice(domain) for domain in domains)
        if args not in seen:
            heldout.append(args)
            seen.add(args)
    return {
        "id": task_id,
        "kind": "synthesis",
        "description": description,
        "params": params,
        "public": [(args, oracle(*args)) for args in examples],
        "heldout": [(args, oracle(*args)) for args in heldout],
        "reference": {lang: dedent(code).strip() + "\n" for lang, code in sources.items()},
    }


def _nearest(n, d):
    return min(range(n + 1), key=lambda k: (abs(d * k - n), k % 2))


def _overlap(a, length_a, b, length_b):
    first = {(a + i) % 12 for i in range(length_a)}
    second = {(b + i) % 12 for i in range(length_b)}
    return len(first & second)


def _descents(n):
    digits = str(n)
    return sum(x > y for x, y in zip(digits, digits[1:]))


def _middle(a, b, c):
    scores = (a, b, c)
    return sorted(range(3), key=lambda i: (scores[i], i))[1] + 1


def _shortfall(stock, day, shipment):
    cumulative = (2, 3, 6, 8, 9, 12, 14)
    return next(
        (i for i, demand in enumerate(cumulative, 1) if stock + shipment * (day <= i) < demand),
        0,
    )


def _fare(seats, member, peak):
    billable = len(range(2 if member else 0, seats))
    per_seat = (5, 5, 5) + (3,) * 12
    return sum(per_seat[:billable]) + 4 * bool(billable and peak)


TASKS = [
    _task(
        "round_ties_even",
        "Return the integer nearest to the exact fraction n/d. When the fraction is halfway "
        "between two integers return the even one. Inputs satisfy 0 <= n <= 60 and 1 <= d <= 12.",
        [("n", "int"), ("d", "int")],
        [(9, 2), (11, 2), (8, 3)],
        [(0, 1), (0, 12), (60, 1), (60, 12), (1, 2), (3, 2), (6, 12), (18, 12),
         (7, 12), (5, 12), (59, 2), (4, 3), (5, 3)],
        [range(61), range(1, 13)],
        _nearest,
        {
            "python": """
                def solve(n: int, d: int) -> int:
                    q, r = divmod(n, d)
                    if 2 * r > d or (2 * r == d and q % 2 == 1):
                        return q + 1
                    return q
            """,
            "rust": """
                fn solve(n: i64, d: i64) -> i64 {
                    let q = n / d;
                    let twice = 2 * (n % d);
                    if twice > d || (twice == d && q % 2 == 1) { q + 1 } else { q }
                }
            """,
            "gpp": """
                fn solve(n: I64, d: I64) -> I64 !{} {
                    let q = n / d;
                    let twice = 2 * (n % d);
                    if twice > d || (twice == d && q % 2 == 1) { return q + 1; }
                    return q;
                }
            """,
        },
    ),
    _task(
        "circular_overlap",
        "A dial has twelve slots numbered 0 through 11, advancing from 11 back to 0. "
        "The first arc starts at a and covers length_a consecutive slots including a. "
        "The second starts at b and covers length_b slots the same way. Zero length covers "
        "no slots. Return the number of slots covered by both arcs. Starts are in [0,11] "
        "and lengths are in [0,12], all endpoints inclusive.",
        [("a", "int"), ("length_a", "int"), ("b", "int"), ("length_b", "int")],
        [(10, 4, 0, 3), (2, 2, 4, 1), (9, 0, 9, 5)],
        [(0, 0, 0, 0), (11, 12, 5, 12), (0, 12, 11, 1), (11, 1, 0, 12),
         (11, 3, 10, 3), (7, 12, 3, 0), (9, 2, 9, 2), (5, 7, 0, 5), (0, 5, 4, 3)],
        [range(12), range(13), range(12), range(13)],
        _overlap,
        {
            "python": """
                def solve(a: int, length_a: int, b: int, length_b: int) -> int:
                    count = 0
                    for slot in range(12):
                        if (slot - a) % 12 < length_a and (slot - b) % 12 < length_b:
                            count += 1
                    return count
            """,
            "rust": """
                fn solve(a: i64, length_a: i64, b: i64, length_b: i64) -> i64 {
                    let mut count = 0;
                    for slot in 0..12 {
                        if (slot + 12 - a) % 12 < length_a && (slot + 12 - b) % 12 < length_b {
                            count += 1;
                        }
                    }
                    count
                }
            """,
            "gpp": """
                fn solve(a: I64, length_a: I64, b: I64, length_b: I64) -> I64 !{} {
                    var count = 0;
                    var slot = 0;
                    while slot < 12 {
                        if (slot + 12 - a) % 12 < length_a && (slot + 12 - b) % 12 < length_b {
                            count = count + 1;
                        }
                        slot = slot + 1;
                    }
                    return count;
                }
            """,
        },
    ),
    _task(
        "digit_descents",
        "Read n in ordinary decimal without leading zeros, from left to right. Return how "
        "many adjacent digit pairs have a strictly larger first digit. Inputs are integers "
        "from 0 through 999999 inclusive.",
        [("n", "int")],
        [(4431,), (1023,), (7,)],
        [(0,), (999999,), (11,), (10,), (12,), (111111,), (100000,), (987654,),
         (123456,), (909090,), (101,), (90,), (9,), (1001,)],
        [range(1000000)],
        _descents,
        {
            "python": """
                def solve(n: int) -> int:
                    count = 0
                    while n >= 10:
                        if n // 10 % 10 > n % 10:
                            count += 1
                        n //= 10
                    return count
            """,
            "rust": """
                fn solve(mut n: i64) -> i64 {
                    let mut count = 0;
                    while n >= 10 {
                        if (n / 10) % 10 > n % 10 { count += 1; }
                        n /= 10;
                    }
                    count
                }
            """,
            "gpp": """
                fn solve(n: I64) -> I64 !{} {
                    var value = n;
                    var count = 0;
                    while value >= 10 {
                        if value / 10 % 10 > value % 10 { count = count + 1; }
                        value = value / 10;
                    }
                    return count;
                }
            """,
        },
    ),
    _task(
        "median_index",
        "Number three entries a, b, c as 1, 2, 3 respectively. Sort entries by increasing "
        "value, breaking equal-value ties by increasing original number. Return the ORIGINAL "
        "number of the entry in the middle position. Each value is in [-4,4] inclusive.",
        [("a", "int"), ("b", "int"), ("c", "int")],
        [(3, 1, 2), (0, 0, -1), (-2, -2, -2)],
        [(-4, 0, 4), (-4, 4, 0), (0, -4, 4), (0, 4, -4), (4, -4, 0), (4, 0, -4),
         (2, 2, 3), (2, 3, 2), (3, 2, 2), (2, 3, 3), (3, 2, 3), (3, 3, 2), (4, 4, 4)],
        [range(-4, 5)] * 3,
        _middle,
        {
            "python": """
                def solve(a: int, b: int, c: int) -> int:
                    if (b < a) != (c < a):
                        return 1
                    if (a <= b) != (c < b):
                        return 2
                    return 3
            """,
            "rust": """
                fn solve(a: i64, b: i64, c: i64) -> i64 {
                    if (b < a) != (c < a) { return 1; }
                    if (a <= b) != (c < b) { return 2; }
                    3
                }
            """,
            "gpp": """
                fn solve(a: I64, b: I64, c: I64) -> I64 !{} {
                    if (b < a) != (c < a) { return 1; }
                    if (a <= b) != (c < b) { return 2; }
                    return 3;
                }
            """,
        },
    ),
    _task(
        "reorder_day",
        "A shop starts with stock units. Daily demand on days 1 through 7 is 2,1,3,2,1,3,2 "
        "units respectively. A single shipment of shipment units arrives before demand on "
        "day number day. Each day deduct that day's demand if it can be met. Return the first "
        "day (1 through 7) whose demand cannot be met, or 0 if all seven can be met. "
        "Input ranges are stock in [0,15], day in [1,7], shipment in [0,6], inclusive.",
        [("stock", "int"), ("day", "int"), ("shipment", "int")],
        [(1, 2, 6), (8, 3, 6), (9, 7, 6)],
        [(0, 1, 2), (1, 1, 1), (1, 2, 0), (0, 7, 6), (15, 7, 0), (13, 7, 1),
         (12, 7, 1), (14, 1, 0), (3, 3, 0), (6, 4, 1), (8, 5, 0), (10, 6, 1)],
        [range(16), range(1, 8), range(7)],
        _shortfall,
        {
            "python": """
                def solve(stock: int, day: int, shipment: int) -> int:
                    for i, demand in enumerate((2, 1, 3, 2, 1, 3, 2), 1):
                        if i == day:
                            stock += shipment
                        if stock < demand:
                            return i
                        stock -= demand
                    return 0
            """,
            "rust": """
                fn solve(mut stock: i64, day: i64, shipment: i64) -> i64 {
                    for i in 1..=7 {
                        if i == day { stock += shipment; }
                        let demand = match i % 3 { 1 => 2, 2 => 1, _ => 3 };
                        if stock < demand { return i; }
                        stock -= demand;
                    }
                    0
                }
            """,
            "gpp": """
                fn solve(stock: I64, day: I64, shipment: I64) -> I64 !{} {
                    var left = stock;
                    var i = 1;
                    while i <= 7 {
                        if i == day { left = left + shipment; }
                        var demand = 3;
                        if i % 3 == 1 { demand = 2; }
                        if i % 3 == 2 { demand = 1; }
                        if left < demand { return i; }
                        left = left - demand;
                        i = i + 1;
                    }
                    return 0;
                }
            """,
        },
    ),
    _task(
        "peak_fare",
        "Return the total price in whole units for seats booked. Members get the first two "
        "seats free. Of the remaining billable seats the first three cost 5 each and every "
        "additional seat costs 3. A peak booking incurs a single extra 4 units if at least "
        "one seat is billable. seats is in [0,12] inclusive. member and peak are booleans.",
        [("seats", "int"), ("member", "bool"), ("peak", "bool")],
        [(6, True, True), (2, True, True), (1, False, False)],
        [(s, m, p) for s in (0, 2, 3, 4, 5, 6, 12) for m in (False, True) for p in (False, True)],
        [range(13), (False, True), (False, True)],
        _fare,
        {
            "python": """
                def solve(seats: int, member: bool, peak: bool) -> int:
                    count = max(0, seats - (2 if member else 0))
                    if count == 0:
                        return 0
                    return 5 * min(count, 3) + 3 * max(count - 3, 0) + (4 if peak else 0)
            """,
            "rust": """
                fn solve(seats: i64, member: bool, peak: bool) -> i64 {
                    let count = seats - if member { 2 } else { 0 };
                    if count <= 0 { return 0; }
                    let base = if count <= 3 { 5 * count } else { 15 + 3 * (count - 3) };
                    base + if peak { 4 } else { 0 }
                }
            """,
            "gpp": """
                fn solve(seats: I64, member: Bool, peak: Bool) -> I64 !{} {
                    var count = seats;
                    if member { count = count - 2; }
                    if count <= 0 { return 0; }
                    var price = 5 * count;
                    if count > 3 { price = 15 + 3 * (count - 3); }
                    if peak { price = price + 4; }
                    return price;
                }
            """,
        },
    ),
]
