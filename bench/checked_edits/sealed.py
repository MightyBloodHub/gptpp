"""Scoring process only. Independent physical/counting oracles and fixed input rosters."""
from itertools import product


def scalar_cases(name):
    if name == "weighbridge":
        # A signed displacement between two ticks is computed by walking the scale.
        for gross, tare in product(range(7, 22), range(0, 22)):
            sign = 1 if gross >= tare else -1
            yield (gross, tare), sign * len(range(min(gross, tare), max(gross, tare)))
    elif name == "service_gap":
        for left, right in product(range(-10, 12), repeat=2):
            if -3 <= left <= 4 and -3 <= right <= 4:
                continue
            first, last = sorted([left, right])
            yield (left, right), len(range(first + 1, last)) == 1
    elif name == "proof_sheet":
        for printed in range(16, 96):
            pages = list(range(printed))
            pages.append(None)
            while len(pages) % 4:
                pages.append(None)
            yield (printed,), pages.count(None)
    else:
        raise ValueError(name)


def machine(name, events):
    if name == "mirror_carriage":
        # Read history backwards: each feed is reflected by every subsequent fold.
        direction, location = 1, 0
        for fold in reversed(events):
            if fold:
                direction *= -1
            else:
                location += direction
        return location
    if name == "feed_hopper":
        scoops = []
        for change in events:
            if change > 0:
                scoops.extend([1] * change)
                del scoops[6:]
            elif 0 < -change <= len(scoops):
                del scoops[change:]
        return len(scoops)
    if name == "seal_press":
        # Since the last cancel, a prime followed eventually by a stamp creates a seal.
        tail = tuple(events)
        if 0 in tail:
            tail = tail[len(tail) - tail[::-1].index(0):]
        if 1 not in tail:
            return 0
        return 2 if 2 in tail[tail.index(1) + 1:] else 1
    raise ValueError(name)


def histories(task):
    # Every prefix state and observable result matters to a caller.
    for n in range(1, 6):
        for events in product(task.events, repeat=n):
            steps = []
            state = task.initial
            for i, event in enumerate(events, 1):
                expected = machine(task.name, events[:i])
                steps.append(((state, event), expected))
                state = expected
            yield events, steps
