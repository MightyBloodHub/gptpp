"""Apply three publication policies to the same table of portable public-fitting candidates."""

from time import monotonic

from engine import BOOL, COMMUTE, INT, OPS_B, OPS_I, operation, probes


def cost(node):
    return 1 + sum(cost(child) for child in node[1:]) if isinstance(node, tuple) else 1


def search(args, result_type, public, answers, deadline, limit=256):
    extra = probes(args)
    inputs = public + extra
    size = len(public)
    seen = {INT: {}, BOOL: {}}
    fits = {}
    first = None
    stats = {
        "vector_evaluations": 0,
        "partition_tests": 0,
        "root_checks": 0,
        "probe_rows": len(extra),
    }

    def register(typ, node, signature):
        nonlocal first
        previous = seen[typ].get(signature)
        if previous is not None and cost(previous) <= cost(node):
            return
        seen[typ][signature] = node
        if typ != result_type or signature[:size] != answers or stats["root_checks"] >= limit:
            return
        stats["root_checks"] += 1
        if first is None:
            first = node
        fits[signature[size:]] = node

    for i, (name, typ) in enumerate(args):
        register(typ, name, tuple(row[i] for row in inputs))
    literals = {0, 1, 2, -1}
    literals.update(v for row in public for v in row if type(v) is int)
    literals.update(v for v in answers if type(v) is int)
    for v in sorted(literals, key=lambda n: (abs(n), n))[:14]:
        register(INT, v, (v,) * len(inputs))
    for v in (False, True):
        register(BOOL, v, (v,) * len(inputs))

    def emit(typ, op, *children):
        stats["vector_evaluations"] += 1
        node = (op, *(item[1] for item in children))
        vector = tuple(operation(op, row) for row in zip(*(c[0] for c in children)))
        register(typ, node, vector)

    def grade(item):
        values, node = item
        matches = sum(type(x) is type(y) and x == y for x, y in zip(values, answers))
        distance = sum(10000 if x is None else min(10000, abs(int(x)-int(y))) for x,y in zip(values,answers))
        return -matches, distance, len(str(node)), str(node)

    def level(pool, cap):
        for item in pool[BOOL]:
            if stats["vector_evaluations"] >= cap:
                return
            emit(BOOL, "not", item)
            emit(INT, "int", item)
        for index in range(max(map(len, pool.values()))):
            for typ, out, ops in ((INT, INT, OPS_I), (INT, BOOL, OPS_B), (BOOL, BOOL, ("and", "or", "==", "!="))):
                if index >= len(pool[typ]):
                    continue
                a = pool[typ][index]
                for j, b in enumerate(pool[typ]):
                    for op in ops:
                        if op in COMMUTE and j < index:
                            continue
                        if stats["vector_evaluations"] >= cap or monotonic() > deadline:
                            return
                        emit(out, op, a, b)

    seed = {k: list(d.items()) for k, d in seen.items()}
    level(seed, 5000)
    pool = {}
    for typ in (INT, BOOL):
        ranked = sorted(seen[typ].items(), key=grade)
        kept = dict(seed[typ] + ranked[:25] + list(seen[typ].items())[:38])
        pool[typ] = list(dict(ranked[:25] + list(kept.items())).items())
    level(pool, 13500)

    ranked = {typ: sorted(values.items(), key=grade) for typ, values in seen.items()}
    for cv, condition in ranked[BOOL][:160]:
        if monotonic() > deadline:
            break
        if None in cv[:size] or len(set(cv[:size])) < 2:
            continue
        yes, no = [], []
        for values, node in ranked[result_type][:300]:
            stats["partition_tests"] += 1
            if all(x == y for flag, x, y in zip(cv, values, answers) if flag):
                yes.append((values, node))
            if all(x == y for flag, x, y in zip(cv, values, answers) if not flag):
                no.append((values, node))
        for a in yes[:3]:
            for b in no[:3]:
                emit(result_type, "if", (cv, condition), a, b)

    stats["distinct_vectors"] = sum(map(len, seen.values()))
    stats["behaviors"] = len(fits)
    stats["time_limit_hit"] = monotonic() > deadline
    lowest = min(map(cost, fits.values()), default=None)
    shortest = [node for node in fits.values() if cost(node) == lowest]
    stats["minimum_cost"] = lowest
    stats["shortest_behaviors"] = len(shortest)
    if stats["time_limit_hit"]:
        return {k: None for k in ("first", "conservative", "minimum")}, stats
    return {
        "first": first,
        "conservative": first if len(fits) == 1 else None,
        "minimum": shortest[0] if len(shortest) == 1 else None,
    }, stats
