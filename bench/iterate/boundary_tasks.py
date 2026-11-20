"""Pre-run task lock for the independent boundary-stop comparison."""

if __package__:
    from .tasks import _expression, _task
else:
    from tasks import _expression, _task


def _blocks(start, length, size):
    return len({address // size for address in range(start, start + length)})


def _server(rallies):
    player = 1
    for completed in range(1, rallies + 1):
        if completed > 16 or completed % 2 == 0:
            player = 3 - player
    return player


def _ascent(height, lift, slip):
    # Day one's peak is lift. Each subsequent morning starts from the
    # previous night's nonnegative balance.
    return next((day for day in range(1, 42)
                 if lift + (day - 1) * max(lift - slip, 0) >= height), -1)


def _lock(secret, guess):
    return sum(a == b for a, b in zip(f"{secret:04d}", f"{guess:04d}"))


def _raster(height, width, row, col):
    original = list(range(width * height))
    rotated = list(reversed(original))
    return rotated[row * width + col]


def _flow(left, right, divisor):
    # Count the complete bundles of excess fluid available to transfer.
    high, low = max(left, right), min(left, right)
    units = sum(1 for _ in range(low + divisor, high + 1, divisor))
    return units if left >= right else -units


def _locker(width, depth):
    limits = [(24, 8), (64, 16)]
    return next((size for size, (area, side) in enumerate(limits, 1)
                 if width * depth <= area and max(width, depth) <= side), 0)


def _fold(width, height, folds):
    sides = [width, height]
    for _ in range(folds):
        sides.sort()
        long = sides[1]
        # Count the grid cells occupied when the two portions are superimposed.
        sides[1] = len({min(i, long - 1 - i) for i in range(long)})
    return sides[0] * sides[1]


TASKS = [
    _task(
        "storage_reads", "expr",
        "Reading length consecutive bytes starts at zero-based byte address start. Storage blocks "
        "hold size bytes each (block 0 spans 0 through size-1). Return the number of distinct blocks "
        "the read touches, including both partial end blocks. An empty read touches no blocks. "
        "start and length are 0..64, size is 1..12 inclusive.",
        [("start", "int"), ("length", "int"), ("size", "int")],
        [((3, 4, 4), 2), ((4, 4, 4), 1), ((21, 0, 6), 0)],
        [(0, 0, 1), (0, 1, 1), (1, 1, 1), (0, 64, 1), (64, 64, 1), (7, 1, 8),
         (7, 2, 8), (8, 1, 8), (8, 8, 8), (8, 9, 8), (4, 8, 4), (4, 9, 4),
         (5, 7, 4), (5, 8, 4), (64, 0, 12), (64, 60, 12), (13, 12, 5), (0, 64, 12),
         (11, 1, 12), (11, 13, 12), (29, 2, 3), (32, 17, 2)], _blocks,
        ("return 0 if length == 0 else (start + length - 1) // size - start // size + 1",
         "return if length == 0 { 0 } else { (start + length - 1) / size - start / size + 1 };"),
    ),
    _task(
        "practice_serve", "expr",
        "Player 1 serves first. During the first 16 rallies switch servers after every two rallies. "
        "After 16 completed rallies player 1 serves next; from then on switch after every single "
        "rally. Return the next server number (1 or 2). The argument rallies counts completed "
        "rallies and is 0..40 inclusive.",
        [("rallies", "int")],
        [((0,), 1), ((6,), 2), ((17,), 2)],
        [(n,) for n in (1, 2, 3, 4, 5, 7, 8, 9, 12, 13, 14, 15, 16, 18, 19, 20, 23, 24, 31, 39, 40)],
        _server,
        ("return 1 + ((rallies // 2) % 2 if rallies < 16 else rallies % 2)",
         "return 1 + (if rallies < 16 { (rallies / 2) % 2 } else { rallies % 2 });"),
    ),
    _task(
        "hoist_day", "body",
        "A hoist starts at zero. Each day it rises lift units; on first reaching or passing height "
        "record that day (starting at 1) and stop. Otherwise it slips slip units overnight without "
        "falling below zero. Return the recorded day or -1 if it can never reach height. height "
        "is 1..40, lift 1..9 and slip 0..9 inclusive.",
        [("height", "int"), ("lift", "int"), ("slip", "int")],
        [((10, 4, 1), 3), ((7, 2, 2), -1), ((4, 5, 9), 1)],
        [(1, 1, 9), (1, 9, 0), (9, 9, 9), (10, 9, 9), (10, 9, 8),
         (40, 1, 0), (40, 1, 1), (40, 9, 8), (39, 8, 6), (13, 4, 1), (14, 4, 1),
         (12, 4, 1), (26, 5, 0), (25, 5, 0), (8, 3, 8), (12, 6, 3), (13, 6, 3),
         (3, 1, 2), (8, 8, 7), (32, 9, 2)], _ascent,
        ("""
        if lift < height and lift <= slip:
            return -1
        day = 1
        peak = lift
        while peak < height:
            peak += lift - slip
            day += 1
        return day
        """, """
        if lift < height && lift <= slip { return -1; }
        var day = 1;
        var peak = lift;
        while peak < height {
            peak = peak + lift - slip;
            day = day + 1;
        }
        return day;
        """),
    ),
    _task(
        "keypad_positions", "body",
        "A keypad compares a secret with a guess as two four-digit decimal codes. Left-pad each "
        "with zeros. Return the count of positions where their digits agree, from 0 to 4. "
        "A matching digit in a different position scores nothing. Both inputs are 0..9999 inclusive.",
        [("secret", "int"), ("guess", "int")],
        [((1212, 2121), 0), ((123, 124), 3), ((10, 10), 4)],
        [(0, 0), (0, 1), (1, 0), (0, 1000), (7, 7000), (11, 1100), (1234, 4321),
         (1234, 1234), (1234, 1235), (1234, 2235), (9009, 9090), (9999, 9998),
         (9999, 0), (9999, 9999), (2222, 2022), (20, 2), (90, 900), (1001, 110), (1030, 3010),
         (1010, 101), (4002, 4022), (5550, 5050)], _lock,
        ("""
        a, b = secret, guess
        count = 0
        for _ in range(4):
            if a % 10 == b % 10:
                count += 1
            a //= 10
            b //= 10
        return count
        """, """
        var a = secret;
        var b = guess;
        var count = 0;
        var i = 0;
        while i < 4 {
            if a % 10 == b % 10 { count = count + 1; }
            a = a / 10;
            b = b / 10;
            i = i + 1;
        }
        return count;
        """),
    ),
    _task(
        "rotate_raster", "expr",
        "A height by width image is stored row-major from index 0. For a display coordinate row,col "
        "the original function mirrored the image horizontally when locating the source pixel. "
        "Change it to rotate the image 180 degrees instead, reversing both rows and columns. "
        "Return the original flat array index. Sizes are 1..9, with 0 <= row < height and 0 <= col < width.",
        [("height", "int"), ("width", "int"), ("row", "int"), ("col", "int")],
        [((2, 3, 0, 0), 5), ((3, 4, 1, 2), 5), ((1, 1, 0, 0), 0)],
        [(h, w, r, c) for h, w in ((1, 8), (7, 1), (4, 5), (5, 4), (9, 9))
         for r in (0, h // 2, h - 1) for c in (0, w // 2, w - 1)], _raster,
        _expression("(height - 1 - row) * width + width - 1 - col"),
        _expression("row * width + width - 1 - col"),
    ),
    _task(
        "equalizer_direction", "expr",
        "A pump command used to transfer only when the left level exceeded the right, one whole "
        "unit of transfer per divisor units of difference. Allow movement in either direction. "
        "Return floor(abs(left - right) / divisor) with a positive sign for left-to-right and "
        "a negative sign for right-to-left. Keep the zero result when levels differ by less than "
        "divisor. Levels are 0..100 and divisor is 2..7 inclusive.",
        [("left", "int"), ("right", "int"), ("divisor", "int")],
        [((4, 15, 3), -3), ((15, 4, 3), 3), ((20, 22, 3), 0)],
        [(0, 0, 2), (100, 100, 7), (0, 100, 2), (100, 0, 7), (0, 1, 2),
         (1, 0, 2), (0, 2, 2), (2, 0, 2), (13, 20, 7), (14, 20, 7), (12, 20, 7),
         (48, 51, 4), (48, 52, 4), (48, 53, 4), (48, 43, 4), (5, 99, 3),
         (99, 5, 3), (11, 18, 2), (18, 11, 2), (35, 72, 5), (32, 32, 6)], _flow,
        ("return (left - right) // divisor if left >= right else -((right - left) // divisor)",
         "return (left - right) / divisor;"),
        ("return (left - right) // divisor if left > right else 0",
         "return if left > right { (left - right) / divisor } else { 0 };"),
    ),
    _task(
        "locker_side_limit", "body",
        "Choose the smallest locker that fits a rectangular parcel. The previous size test used "
        "area only: area <= 24 for small (return 1), area <= 64 for medium (return 2), otherwise "
        "return 0. Add a maximum per-side length of 8 for small and 16 for medium. Both the area "
        "and side limits must hold for the chosen locker; return 0 if neither fits. Both dimensions "
        "are integers in 1..30 inclusive.",
        [("width", "int"), ("depth", "int")],
        [((2, 9), 2), ((20, 1), 0), ((4, 6), 1)],
        [(1, 1), (1, 8), (8, 1), (3, 8), (8, 3), (4, 7), (5, 5), (8, 8),
         (8, 9), (9, 8), (1, 9), (9, 1), (2, 12), (12, 2), (4, 16), (16, 4),
         (3, 17), (17, 3), (1, 17), (30, 1), (30, 30), (6, 11)], _locker,
        ("""
        area = width * depth
        longest = max(width, depth)
        if area <= 24 and longest <= 8:
            return 1
        if area <= 64 and longest <= 16:
            return 2
        return 0
        """, """
        let area = width * depth;
        if area <= 24 && width <= 8 && depth <= 8 { return 1; }
        if area <= 64 && width <= 16 && depth <= 16 { return 2; }
        return 0;
        """),
        ("""
        area = width * depth
        if area <= 24:
            return 1
        if area <= 64:
            return 2
        return 0
        """, """
        let area = width * depth;
        if area <= 24 { return 1; }
        if area <= 64 { return 2; }
        return 0;
        """),
    ),
    _task(
        "folded_footprint", "body",
        "Fold a sheet the specified number of times. Each fold halves the longer side; on a tie halve the width. "
        "Previously the reduced side was rounded down, with minimum 1. Change it to round up "
        "instead, leaving the other side untouched. Determine the longer side again before each "
        "fold. Return the final area. width and height are 1..40 and folds is 0..8 inclusive.",
        [("width", "int"), ("height", "int"), ("folds", "int")],
        [((5, 3, 1), 9), ((8, 4, 2), 8), ((3, 3, 0), 9)],
        [(1, 1, 0), (1, 1, 8), (1, 2, 1), (1, 3, 1), (3, 1, 1), (3, 3, 1),
         (3, 3, 2), (3, 5, 2), (5, 7, 2), (9, 4, 3), (9, 5, 3), (12, 12, 4),
         (16, 8, 0), (16, 8, 4), (40, 1, 8), (40, 40, 1), (39, 40, 4),
         (7, 9, 4), (2, 2, 8), (11, 13, 5), (39, 39, 6), (15, 4, 3)], _fold,
        ("""
        w, h = width, height
        for _ in range(folds):
            if w >= h:
                w = (w + 1) // 2
            else:
                h = (h + 1) // 2
        return w * h
        """, """
        var w = width;
        var h = height;
        var i = 0;
        while i < folds {
            if w >= h { w = (w + 1) / 2; } else { h = (h + 1) / 2; }
            i = i + 1;
        }
        return w * h;
        """),
        ("""
        w, h = width, height
        for _ in range(folds):
            if w >= h:
                w = max(1, w // 2)
            else:
                h = max(1, h // 2)
        return w * h
        """, """
        var w = width;
        var h = height;
        var i = 0;
        while i < folds {
            if w >= h { w = w / 2; } else { h = h / 2; }
            if w == 0 { w = 1; }
            if h == 0 { h = 1; }
            i = i + 1;
        }
        return w * h;
        """),
    ),
]
