"""Frozen small contracts, bounded domains, sparse examples and language-matched expressions."""

from dataclasses import dataclass
from itertools import product


@dataclass(frozen=True)
class Fixture:
    target: str
    signature: str
    binders: str
    result_type: str
    names: tuple
    domains: tuple
    property: str
    original: tuple
    menu: tuple
    public: tuple
    extra: tuple

    def tuples(self):
        return list(product(*self.domains))

    def module(self):
        return (f"module study.contracts;\n\nfn {self.target}({self.signature}) -> {self.result_type} !{{}} "
                f"{{ return {self.original[0]}; }}\n"
                "pub fn main() -> I64 !{} { return 0; }\n"
                f"contract rule({self.binders}) {{ {self.property} }}\n")


def native(expr):
    return (expr, expr, expr)


TASKS = [
    Fixture(
        "offset_tick", "offset: I64, carry: Bool", "offset: I64 in -3..=4, carry: Bool", "I64",
        ("offset", "carry"), (range(-3, 5), (False, True)),
        "if carry { offset_tick(offset, carry) - 1 == offset } else { offset_tick(offset, carry) == offset }",
        native("offset"),
        (
            native("offset + 1"),
            ("if offset < 0 { offset } else { offset + (carry as I64) }",
             "offset if offset < 0 else offset + int(carry)",
             "if offset < 0 { offset } else { offset + (carry as i64) }"),
            ("offset + (carry as I64)", "offset + int(carry)", "offset + (carry as i64)"),
            ("min(offset, 4) + (carry as I64)", "min(offset, 4) + int(carry)", "offset.min(4) + (carry as i64)"),
        ),
        ((1, True), (3, True)), ((-12, False), (-8, True), (6, False), (6, True), (100, True)),
    ),
    Fixture(
        "has_room", "used: I64, limit: I64", "used: I64 in 0..=4, limit: I64 in 0..=4", "Bool",
        ("used", "limit"), (range(5), range(5)),
        "has_room(used, limit) == (limit - used > 0)", native("used <= limit"),
        (native("used != limit"), native("used == 1"), native("used < limit")),
        ((2, 2), (1, 3)), ((5, 5), (6, 5), (5, 6), (20, 30), (31, 30)),
    ),
    Fixture(
        "block_index", "offset: I64, last_lane: I64", "offset: I64 in 0..=7, last_lane: I64 in 0..=3",
        "I64", ("offset", "last_lane"), (range(8), range(4)),
        "block_index(offset, last_lane) * (last_lane + 1) <= offset && "
        "(block_index(offset, last_lane) + 1) * (last_lane + 1) > offset",
        ("offset / last_lane", "offset // last_lane", "offset / last_lane"),
        (native("0"), ("offset / (last_lane + 2)", "offset // (last_lane + 2)", "offset / (last_lane + 2)"),
         ("offset / (last_lane + 1)", "offset // (last_lane + 1)", "offset / (last_lane + 1)")),
        ((0, 0), (2, 2)), ((15, 0), (16, 3), (31, 6), (99, 10), (128, 127)),
    ),
]


def oracle(task, args):
    a, b = args
    if task.target == "offset_tick":
        return (a, a + 1)[b]
    if task.target == "has_room":
        return a in range(b)
    if task.target == "block_index":
        return divmod(a, b + 1)[0]
    raise ValueError(task.target)
