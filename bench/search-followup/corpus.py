"""Finite-domain adaptations of published CodingBat rules, with independent specifications."""

from collections import Counter
from dataclasses import dataclass
from itertools import permutations, product, takewhile
from random import Random


@dataclass(frozen=True)
class Task:
    name: str
    source: str
    args: tuple
    result: str
    request: str
    old: str
    reference: str
    domains: tuple
    examples: tuple
    initial: None = None
    events: tuple = ()


I64, BOOL = "I64", "Bool"
FLAGS = (False, True)


def inclusive(low, high):
    return tuple(range(low, high + 1))


def integers(names):
    return tuple((name, I64) for name in names.split())


def three_sum(terms):
    return " + ".join(f"({term})" for term in terms)


ABC = integers("a b c")
small = inclusive(-2, 5)
with_sentinel = (0, 1, 2, 3, 4, 7, 12, 13, 14, 18)
teen_values = (0, 1, 2, 3, 10, 12, 13, 14, 15, 16, 17, 18, 19, 20, 23)
absolute = lambda a, b: f"max({a} - {b}, {b} - {a})"
near_b = f"{absolute('a', 'b')} <= 1 and {absolute('a', 'c')} >= 2"
near_c = f"{absolute('a', 'c')} <= 1 and {absolute('a', 'b')} >= 2"

TASKS = (
    Task("makeBricks", "p183562", integers("small big goal"), BOOL,
         "Decide whether an exact target length can be built with the available unit bricks and five-unit bricks. Counts and the target are nonnegative.",
         "small + big * 5 >= goal", "small >= goal - 5 * min(big, goal // 5)",
         (inclusive(0, 7), inclusive(0, 4), inclusive(0, 24)), ((3, 1, 8), (3, 1, 9), (3, 2, 10))),
    Task("loneSum", "p148972", ABC, I64,
         "Sum the three values, dropping every occurrence of a number that occurs more than once.",
         "a + b + c", three_sum(f"{v} if {v} != {x} and {v} != {y} else 0" for v,x,y in ("abc","bca","cab")),
         (small,)*3, ((1,2,3),(3,2,3),(3,3,3))),
    Task("luckySum", "p130788", ABC, I64,
         "Read left to right and sum up to, but excluding, the first value of 13. Sum all three if 13 never appears.",
         "a + b + c", "0 if a == 13 else a + (0 if b == 13 else b + (0 if c == 13 else c))",
         (with_sentinel,)*3, ((1,2,3),(1,2,13),(1,13,3))),
    Task("noTeenSum", "p182879", ABC, I64,
         "Sum three numbers. Omit 13, 14, 17, 18 and 19 wherever they occur. Keep 15 and 16.",
         "a + b + c", three_sum(f"{v} if {v} < 13 or {v} > 19 or {v} == 15 or {v} == 16 else 0" for v in "abc"),
         (teen_values,)*3, ((1,2,3),(2,13,1),(2,1,14))),
    Task("roundSum", "p186753", ABC, I64,
         "Round each nonnegative input separately to its nearest ten, with halves rounded up. Add the rounded values.",
         "a + b + c", three_sum(f"(({v} + 5) // 10) * 10" for v in "abc"),
         (inclusive(0,21),)*3, ((16,17,18),(12,13,14),(6,4,4))),
    Task("closeFar", "p138990", ABC, BOOL,
         "Exactly one of b and c must be within one unit of a. The other must be at least two units from each of the other two values.",
         "a == b", f"(({near_b}) or ({near_c})) and {absolute('b','c')} >= 2",
         (inclusive(-3,9),)*3, ((1,2,10),(1,2,3),(4,1,3))),
    Task("blackjack", "p117019", integers("a b"), I64,
         "From two positive totals select the largest total of at most 21. Return zero when both are too large.",
         "max(a, b)", "max(a if a <= 21 else 0, b if b <= 21 else 0)",
         (inclusive(1,30),)*2, ((19,21),(21,19),(19,22))),
    Task("evenlySpaced", "p198700", ABC, BOOL,
         "Determine whether the three integers, after ordering, have equal consecutive gaps. A triple of equal values qualifies.",
         "a + b == 2 * c", "a + b == 2 * c or b + c == 2 * a or a + c == 2 * b",
         (inclusive(-3,9),)*3, ((2,4,6),(4,6,2),(4,6,3))),
    Task("cigarParty", "p159531", (("count",I64),("weekend",BOOL)), BOOL,
         "A gathering needs at least 40 items. On weekdays it also requires no more than 60 items. Count is nonnegative.",
         "count >= 40", "count >= 40 and (weekend or count <= 60)",
         (inclusive(25,80),FLAGS), ((30,False),(50,False),(70,True))),
    Task("dateFashion", "p103360", integers("you date"), I64,
         "Two style scores range from zero to ten. Return 0 if either score is at most two, otherwise 2 if at least one score is eight or higher, and 1 otherwise.",
         "1", "0 if min(you, date) <= 2 else (2 if max(you, date) >= 8 else 1)",
         (inclusive(0,10),)*2, ((5,10),(5,2),(5,5))),
    Task("caughtSpeeding", "p157733", (("speed",I64),("birthday",BOOL)), I64,
         "Classify speed into tier 0 through 60, tier 1 from 61 through 80, and tier 2 above 80. Increase both cutoffs by five on a birthday.",
         "int(speed > 60)", "int(speed > 60 + 5 * int(birthday)) + int(speed > 80 + 5 * int(birthday))",
         (inclusive(42,99),FLAGS), ((60,False),(65,False),(65,True))),
    Task("sortaSum", "p183071", integers("a b"), I64,
         "Add two integers. Replace any total from 10 through 19, inclusive, with 20.",
         "a + b", "20 if a + b >= 10 and a + b <= 19 else a + b",
         (inclusive(-5,22),)*2, ((3,4),(9,4),(10,11))),
)


def expected(t, values):
    """Independent small-domain implementations, distinct from the typed reference expressions."""
    if t.name == "makeBricks":
        small, big, goal = values
        return goal in {u + 5*v for u in range(small+1) for v in range(big+1)}
    if t.name == "loneSum":
        return sum(v for v, count in Counter(values).items() if count == 1)
    if t.name == "luckySum":
        return sum(takewhile(lambda n: n != 13, values))
    if t.name == "noTeenSum":
        return sum(v for v in values if v not in {13,14,17,18,19})
    if t.name == "roundSum":
        return sum(min(range(0,41,10), key=lambda ten: (abs(v-ten), -ten)) for v in values)
    if t.name == "closeFar":
        a, b, c = values
        return any(far not in range(a-1,a+2) and far not in range(near-1,near+2)
                   and near in range(a-1,a+2) for near,far in permutations((b,c)))
    if t.name == "blackjack":
        return max([0, *(n for n in values if n in range(1,22))])
    if t.name == "evenlySpaced":
        first,middle,last = sorted(values)
        return middle-first == last-middle
    if t.name == "cigarParty":
        count, weekend = values
        return count in range(40,81 if weekend else 61)
    if t.name == "dateFashion":
        ranks = [0 if v in range(3) else (2 if v in (8,9,10) else 1) for v in values]
        return 0 if 0 in ranks else max(ranks)
    if t.name == "caughtSpeeding":
        speed,birthday = values
        adjusted = speed - (5 if birthday else 0)
        return next(i for i,limit in enumerate((60,80,999)) if adjusted <= limit)
    if t.name == "sortaSum":
        total = sum(values)
        return {n:20 for n in range(10,20)}.get(total,total)
    raise KeyError(t.name)


def direct(t):
    return list(product(*t.domains))


def cases(t):
    domain = direct(t)
    shuffled = list(domain)
    Random(117403+TASKS.index(t)).shuffle(shuffled)
    sample = list(t.examples) + [domain[0],domain[-1]]
    if t.result == BOOL:
        for label in (False,True):
            sample.extend(row for row in [r for r in shuffled if expected(t,r) is label][:5])
    for row in shuffled:
        if len(set(sample)) >= 24:
            break
        sample.append(row)
    visible = list(dict.fromkeys(sample))
    public_set = set(visible)
    return visible, [row for row in domain if row not in public_set]


def histories(t):
    return []


def history_expected(t, seq):
    raise ValueError("This externally sourced block has scalar inputs.")
