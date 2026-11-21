"""Public assignment packets. The edit is one scalar expression, including in transition tasks."""

from dataclasses import dataclass
from itertools import product


@dataclass(frozen=True)
class Task:
    name: str
    args: tuple
    result: str
    bounds: tuple
    request: str
    previous: str
    examples: tuple  # Hand-labeled commissioning checks, visible to search and model.
    predicate: str  # Public acceptance rule, with "out" denoting update's result.
    reference: str  # Author-authorized reference, used for calibration and one question.
    initial: int | None = None
    events: tuple = ()

    @property
    def stateful(self):
        return self.initial is not None


I = "I64"
B = "Bool"
TASKS = (
    Task("weighbridge", (("gross", I), ("tare", I)), I, ((0, 6), (0, 5)),
         "Return the signed net reading. Adding the tare back to the result must reproduce gross, even after a downward calibration.",
         "gross", (((3, 1), 2), ((1, 3), -2), ((4, 0), 4), ((5, 5), 0)),
         "out + tare == gross", "gross - tare"),
    Task("service_gap", (("left", I), ("right", I)), B, ((-3, 4), (-3, 4)),
         "Permit service exactly when there is one unused integer position strictly between the two anchors. Either anchor can be on the left.",
         "left == right", (((0, 2), True), ((1, 2), False), ((1, 4), False), ((2, 4), True)),
         "out == (max(left, right) - min(left, right) == 2)",
         "left == right + 2 || right == left + 2"),
    Task("proof_sheet", (("printed", I),), I, ((0, 15),),
         "Append blank pages so the finished proof has a multiple of four pages. Use the smallest positive number of blanks. Even an aligned proof needs a blank for the stamp.",
         "0", (((1,), 3), ((2,), 2), ((3,), 1), ((6,), 2)),
         "out >= 1 && out <= 4 && (printed + out) % 4 == 0", "4 - printed % 4"),
    Task("mirror_carriage", (("offset", I), ("fold", B)), I, ((-4, 4), (False, True)),
         "The carriage starts at offset zero. A feed advances its signed offset by one. A fold reflects the current offset across zero, without feeding. Return the offset after each event.",
         "offset + 1", (((0, False), 1), ((2, False), 3), ((1, True), -1), ((-2, True), 2)),
         "if fold { out + offset == 0 } else { out - offset == 1 }",
         "if fold { -offset } else { offset + 1 }", 0, (False, True)),
    Task("feed_hopper", (("held", I), ("change", I)), I, ((0, 6), (-3, 3)),
         "A hopper starts empty and holds six scoops. Pouring discards excess above six. A withdrawal must be filled in full. If there are too few scoops, reject it and keep the old level. Return the level after each operation.",
         "held + change", (((1, -1), 0), ((2, 2), 4), ((5, 3), 6), ((0, -2), 0)),
         "if held + change < 0 { out == held } else { out == min(6, held + change) }",
         "if change < -held { held } else { min(held + change, 6) }", 0, (-3, -1, 0, 2, 3)),
    Task("seal_press", (("phase", I), ("key", I)), I, ((0, 2), (0, 2)),
         "A seal press starts idle (0). Cancel (key 0) always returns to idle. Prime (key 1) arms an idle press (1), leaves an armed one armed, and leaves a sealed one sealed (2). Stamp (key 2) seals an armed press. Stamping in any other phase leaves that phase alone.",
         "key", (((0, 1), 1), ((1, 2), 2), ((2, 0), 0), ((2, 2), 2)),
         "if key == 0 { out == 0 } else if key == 1 { out == max(phase, 1) } else { out == (if phase == 1 { 2 } else { phase }) }",
         "if key == 0 { 0 } else if key == 1 && phase == 0 { 1 } else if key == 2 && phase == 1 { 2 } else { phase }",
         0, (0, 1, 2)),
)


def literal(value):
    return str(value).lower()


def points(task):
    return product(*(range(lo, hi + 1) if type(lo) is int else (False, True) for lo, hi in task.bounds))


def public_answer(task, xs):
    """Authorized public specification executable independently of the edit. No scoring inputs."""
    x, *rest = xs
    if task.name == "weighbridge":
        return x - rest[0]
    if task.name == "service_gap":
        return abs(x - rest[0]) == 2
    if task.name == "proof_sheet":
        return next(n for n in range(1, 5) if (n + x) % 4 == 0)
    y = rest[0]
    if task.name == "mirror_carriage":
        return -x if y else x + 1
    if task.name == "feed_hopper":
        return x if x + y < 0 else min(x + y, 6)
    if task.name == "seal_press":
        return ((0, 1, 0), (0, 1, 2), (0, 2, 2))[x][y]
    raise ValueError(task.name)


def signature(task):
    return ", ".join(f"{name}: {ty}" for name, ty in task.args)


def sketch(task):
    fn = f"fn update({signature(task)}) -> {task.result} !{{}} {{ return ?change: {task.result}; }}"
    checks = [f"contract sample_{i}() {{ update({', '.join(map(literal, xs))}) == {literal(y)} }}"
              for i, (xs, y) in enumerate(task.examples)]
    return "\n".join(["module pilot.edit;", fn, "pub fn main() -> I64 !{} { return 0; }", *checks, ""])


def obligation(task):
    domains = [name + (f": I64 in {low}..={high}" if ty == I else ": Bool")
               for (name, ty), (low, high) in zip(task.args, task.bounds, strict=True)]
    call = "update(" + ", ".join(name for name, _ in task.args) + ")"
    # The predicate uses one target call per occurrence, which also exposes the trace to the repair loop.
    import re
    predicate = re.sub(r"\bout\b", call, task.predicate)
    return dict(name="accept_edit", mode="finite", rule=task.request,
                declaration=f"contract accept_edit({', '.join(domains)}) {{ {predicate} }}",
                limitation="Only the enumerated input domain is verified. Longer histories and other inputs are outside this check.")
