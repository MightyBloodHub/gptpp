"""Final prespecified, disjoint contiguous blocks of external scalar exercises."""

from dataclasses import dataclass
from itertools import product
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


def integers(names):
    return tuple((name,"I64") for name in names.split())


def inclusive(lo,hi):
    return tuple(range(lo,hi+1))


B = "Bool"
I = "I64"
FLAGS = (False,True)
TWO = integers("a b")
ONE = integers("n")
TASKS = (
    Task("love6","p137742",TWO,B,
         "Accept when a value is 6, the sum is 6, or the distance between the values is 6.",
         "a + b == 6","a == 6 or b == 6 or a + b == 6 or a - b == 6 or b - a == 6",
         (inclusive(-8,15),)*2,((6,4),(4,5),(1,5))),
    Task("in1To10","p137365",(("n",I),("outside",B)),B,
         "In normal mode accept every integer from 1 to 10 inclusive. Outside mode accepts numbers at or beyond either endpoint, including 1 and 10.",
         "n >= 1 and n <= 10","(n <= 1 or n >= 10) if outside else (n >= 1 and n <= 10)",
         (inclusive(-12,22),FLAGS),((5,False),(11,False),(11,True))),
    Task("specialEleven","p100962",ONE,B,
         "Accept a nonnegative integer if it equals an eleven-multiple or the integer immediately after one.",
         "n % 11 == 0","n % 11 < 2",(inclusive(0,99),),((22,),(23,),(24,))),
    Task("more20","p118290",ONE,B,
         "Accept a nonnegative integer if adding one or two to a multiple of twenty would produce it.",
         "n % 20 == 1","n % 20 == 1 or n % 20 == 2",(inclusive(0,100),),((20,),(21,),(22,))),
    Task("old35","p159612",ONE,B,
         "Accept a nonnegative integer divisible by exactly one of 3 and 5.",
         "n % 3 == 0","(n % 3 == 0) != (n % 5 == 0)",(inclusive(0,99),),((3,),(10,),(15,))),
    Task("sumDouble","p154485",TWO,I,
         "Add two integers, doubling the total when the two inputs are equal.",
         "a + b","2 * (a + b) if a == b else a + b",(inclusive(-6,14),)*2,((1,2),(3,2),(2,2))),
    Task("diff21","p116624",ONE,I,
         "Return the distance from n to 21, and charge twice that distance if n exceeds 21.",
         "max(21 - n, n - 21)","2 * (n - 21) if n > 21 else 21 - n",(inclusive(-12,72),),((19,),(10,),(21,))),
    Task("parrotTrouble","p140449",(("talking",B),("hour",I)),B,
         "A talking parrot is a problem before 07:00 and after 20:00. The hour is a whole number in the 24-hour day.",
         "talking","talking and (hour < 7 or hour > 20)",(FLAGS,inclusive(0,23)),((True,6),(True,7),(False,6))),
    Task("makes10","p182873",TWO,B,
         "Accept when either input is ten or when their sum equals ten.",
         "a + b == 10","a == 10 or b == 10 or a + b == 10",(inclusive(-5,18),)*2,((9,10),(9,9),(1,9))),
    Task("nearHundred","p184004",ONE,B,
         "Accept numbers within ten units, endpoints included, of either 100 or 200.",
         "n >= 90 and n <= 110","(n >= 90 and n <= 110) or (n >= 190 and n <= 210)",
         (inclusive(65,235),),((93,),(90,),(89,))),
    Task("posNeg","p159227",(("a",I),("b",I),("negative",B)),B,
         "Normally require one strictly positive integer and one strictly negative integer. In negative mode require both integers to be negative. Zero has neither sign.",
         "a < 0 and b < 0","(a < 0 and b < 0) if negative else (a * b < 0)",
         (inclusive(-6,6),inclusive(-6,6),FLAGS),((1,-1,False),(-1,1,False),(-4,-5,True))),
)


def expected(t, values):
    if t.name == "love6":
        a,b = values
        return 6 in {a,b,sum(values),abs(a-b)}
    if t.name == "in1To10":
        n,outside = values
        return n not in range(2,10) if outside else n in range(1,11)
    if t.name == "specialEleven":
        return values[0] in {v+d for v in range(0,111,11) for d in (0,1)}
    if t.name == "more20":
        return values[0] in {v+d for v in range(0,121,20) for d in (1,2)}
    if t.name == "old35":
        a = set(range(0,101,3))
        b = set(range(0,101,5))
        return values[0] in a.symmetric_difference(b)
    if t.name == "sumDouble":
        return sum(values * (2 if len(set(values)) == 1 else 1))
    if t.name == "diff21":
        n, = values
        distance = abs(n-21)
        return sum(distance for _ in range(1 + int(n>21)))
    if t.name == "parrotTrouble":
        talking,hour = values
        quiet_hours = set(range(24)) - set(range(7,21))
        return bool(talking and hour in quiet_hours)
    if t.name == "makes10":
        return 10 in {*values,sum(values)}
    if t.name == "nearHundred":
        return values[0] in set(range(90,111)).union(range(190,211))
    if t.name == "posNeg":
        a,b,mode = values
        signs = tuple((n>0)-(n<0) for n in (a,b))
        return signs == (-1,-1) if mode else set(signs) == {-1,1}
    raise KeyError(t.name)


def direct(t):
    return list(product(*t.domains))


def cases(t):
    domain = direct(t)
    shuffled = list(domain)
    Random(146911+TASKS.index(t)).shuffle(shuffled)
    sample = list(t.examples) + [domain[0],domain[-1]]
    if t.result == B:
        for label in (False,True):
            sample.extend([row for row in shuffled if expected(t,row) is label][:5])
    for row in shuffled:
        if len(set(sample)) >= 24:
            break
        sample.append(row)
    public=list(dict.fromkeys(sample))
    public_set=set(public)
    return public,[row for row in domain if row not in public_set]


def histories(t):
    return []


def history_expected(t,seq):
    raise ValueError("The confirmation block is scalar.")
