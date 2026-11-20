"""Three locally authored arithmetic contracts frozen for the new-task block."""

from bench.policy.fresh import _task


def fixture(name, target, params, description, starter, reference, callers, oracle, public, withheld):
    def label(rows):
        return [(i, args, oracle[i](*args)) for i, args in rows]
    return _task(name, "body", target, params, description, None, "Locally authored scalar contract",
                 starter, reference, callers, label(public), label(withheld))


def clamp(a, b):
    return max(-100, min(100, a + b))


CLAMP = fixture(
    "bounded_accumulator", "adjust", "balance delta",
    "Add the signed delta to balance. Clamp the resulting balance to the closed interval [-100, 100]. "
    "Both inputs are integers in [-1000, 1000]. Downstream updates apply the same rule after each adjustment.",
    ("total = balance + delta\nreturn total", "let total = balance + delta;\nreturn total;"),
    ("total = balance + delta\nreturn max(-100, min(100, total))",
     "let total = balance + delta;\nreturn if total > 100 { 100 } else { if total < -100 { -100 } else { total } };"),
    [("two_adjustments", "start first second", "return adjust(adjust(start, first), second)",
      "return adjust(adjust(start, first), second);"),
     ("declined_amount", "balance delta", "return balance + delta - adjust(balance, delta)",
      "return balance + delta - adjust(balance, delta);")],
    (clamp, lambda a, b, c: clamp(clamp(a, b), c), lambda a, b: a+b-clamp(a,b)),
    [(0, (65, -20)), (1, (94, 40, -25)), (2, (-70, -60))],
    [(0, (1000, -1)), (0, (-1000, 1)), (0, (2, 98)), (0, (-2, -98)), (0, (-50, 51)),
     (0, (0, 0)), (1, (-98, -5, 100)), (1, (-25, 170, -220)), (1, (95, 6, -6)),
     (2, (-95, -5)), (2, (99, 3)), (2, (25, -160))],
)


def ticks(ms):
    whole, remainder = divmod(ms, 1000)
    return whole + bool(remainder)


TICKS = fixture(
    "timeout_quantization", "delay_ticks", "milliseconds",
    "A scheduler wakes only on whole-second ticks. Convert a nonnegative delay in milliseconds to the "
    "smallest number of ticks that covers the full delay. Zero means no wait. Inputs are at most 10,000,000.",
    ("return milliseconds // 1000", "return milliseconds / 1000;"),
    ("return (milliseconds + 999) // 1000", "return (milliseconds + 999) / 1000;"),
    [("wake_tick", "now delay", "return now + delay_ticks(delay)", "return now + delay_ticks(delay);"),
     ("serial_wait", "first second", "return delay_ticks(first) + delay_ticks(second)",
      "return delay_ticks(first) + delay_ticks(second);")],
    (ticks, lambda now, delay: now + ticks(delay), lambda a,b: ticks(a) + ticks(b)),
    [(0, (0,)), (1, (80, 2001)), (2, (900, 1000))],
    [(0, (1,)), (0, (999,)), (0, (1000,)), (0, (1500,)), (0, (9999999,)), (0, (10000000,)),
     (1, (3, 0)), (1, (1200, 4510)), (1, (8, 12000)), (2, (1, 1)), (2, (1000, 2000)), (2, (0, 3101))],
)


def inside(point, lo, hi):
    return int(point in range(lo, hi))


WINDOW = fixture(
    "half_open_windows", "in_window", "point start end",
    "Return 1 when the point is in the window and 0 otherwise. Windows include their start and exclude "
    "their end. End is at least start; an empty window contains no point. Coordinates are integers in [-1000,1000].",
    ("return 1 if start < point and point < end else 0", "return if start < point && point < end { 1 } else { 0 };"),
    ("return 1 if start <= point and point < end else 0", "return if start <= point && point < end { 1 } else { 0 };"),
    [("adjacent_count", "point first split last",
      "return in_window(point, first, split) + in_window(point, split, last)",
      "return in_window(point, first, split) + in_window(point, split, last);"),
     ("credit_in_window", "value point start end", "return value * in_window(point, start, end)",
      "return value * in_window(point, start, end);")],
    (inside, lambda p,a,b,c: inside(p,a,b)+inside(p,b,c), lambda v,p,a,b: v*inside(p,a,b)),
    [(0, (12, 7, 12)), (1, (-4, -9, -4, 3)), (2, (8, 5, 2, 8))],
    [(0, (0, 0, 0)), (0, (1, 1, 2)), (0, (-2, -1, 2)), (0, (2, -3, 2)),
     (0, (-1000, -1000, -999)), (0, (999, -1000, 1000)), (1, (4, 4, 4, 7)),
     (1, (-5, -12, -5, -5)), (1, (6, 0, 2, 5)), (2, (-8, -2, -2, 1)),
     (2, (12, 4, 0, 4)), (2, (0, 2, 1, 3))],
)

TASKS = [CLAMP, TICKS, WINDOW]
