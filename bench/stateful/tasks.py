"""Four independently authored state-transition changes. Oracles consume event histories."""

from dataclasses import dataclass
from itertools import groupby, product


@dataclass(frozen=True)
class Task:
    name: str
    fields: tuple
    initial: tuple
    actions: tuple
    branches: tuple
    old: str
    reference: str
    result_type: str
    request: str
    public: tuple


# A branch gives native-neutral expressions for each next-state field. Exactly one field is a hole.
TASKS = [
    Task("reading_marker", (("page", "I64"), ("mark", "I64")), (0, 0), ("Advance", "Mark", "Recall"),
         (("min(4, s.page + 1)", "s.mark"), ("s.page", "s.page"), ("s.mark", "?")),
         "s.mark", "s.page", "I64",
         "Change Recall to exchange the current page and its bookmark. Two successive recalls restore "
         "the previous pair. Advance still stops at page 4. Mark still copies the current page.",
         ("C", "AC", "ABACC", "BA")),
    Task("pair_dispatch", (("waiting", "I64"), ("sent", "I64")), (0, 0), ("Load", "Dispatch", "Discard"),
         (("min(3, s.waiting + 1)", "s.sent"), ("?", "s.sent + bit(s.waiting >= 2)"), ("0", "s.sent")),
         "0", "s.waiting % 2", "I64",
         "Each Dispatch may send one complete pair from the waiting items. Leave any unpaired item waiting. "
         "Load still holds at most 3 items and Discard still drops the waiting items without shipping.",
         ("B", "AB", "AAB", "AAAB", "ACA")),
    Task("run_record", (("streak", "I64"), ("best", "I64")), (0, 0), ("Hit", "Miss", "Restart"),
         (("s.streak + 1", "?"), ("0", "s.best"), ("0", "0")),
         "max(s.best, s.streak)", "max(s.best, s.streak + 1)", "I64",
         "Update the longest hit run immediately on every Hit, including the hit just received. "
         "Miss ends only the ongoing run. Restart clears both counters.",
         ("A", "AABA", "AC", "BA")),
    Task("armed_toggle", (("armed", "Bool"), ("lit", "Bool")), (False, False), ("Arm", "Tap", "Clear"),
         (("true", "s.lit"), ("false", "?"), ("false", "false")),
         "s.lit OR s.armed", "s.lit != s.armed", "Bool",
         "An armed Tap toggles the lamp. An unarmed Tap leaves the lamp as it was. Every Tap consumes "
         "the arming, Arm leaves the lamp as it was, and Clear turns the lamp off and disarms it.",
         ("B", "AB", "ABB", "ABAB", "C")),
]


def oracle(task, trace):
    """History-level specifications use mutable objects independently of each native step expression."""
    if task.name == "reading_marker":
        # Swap the roles of physical pointers on Recall instead of assigning two expressions.
        positions, current = [0, 0], 0
        for e in trace:
            if e == "A":
                positions[current] = min(positions[current] + 1, 4)
            elif e == "B":
                positions[1-current] = positions[current]
            else:
                current = 1-current
        return positions[current], positions[1-current]
    if task.name == "pair_dispatch":
        waiting, shipments = [], []
        for i, e in enumerate(trace):
            if e == "A" and len(waiting) < 3:
                waiting.append(i)
            elif e == "B" and len(waiting) >= 2:
                shipments.append((waiting.pop(0), waiting.pop(0)))
            elif e == "C":
                waiting.clear()
        return len(waiting), len(shipments)
    if task.name == "run_record":
        since_restart = trace.rsplit("C", 1)[-1]
        groups = [len(list(g)) for name, g in groupby(since_restart) if name == "A"]
        suffix = len(since_restart) - len(since_restart.rstrip("A"))
        return suffix, max(groups, default=0)
    if task.name == "armed_toggle":
        since_clear = trace.rsplit("C", 1)[-1]
        # A consumed arm occupies the gap before a Tap and since the preceding Tap.
        gaps = since_clear.split("B")
        return "A" in gaps[-1], sum("A" in gap for gap in gaps[:-1]) % 2 == 1
    raise ValueError(task.name)


def withheld(task):
    return ["".join(seq) for n in range(1, 7) for seq in product("ABC", repeat=n)
            if "".join(seq) not in task.public]
