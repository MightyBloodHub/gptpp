"""Bounded scalar extracts of three upstream fixes. See upstream-sources.md."""

from calendar import monthrange
from decimal import Decimal, ROUND_HALF_UP

from bench.policy.fresh import _task


def _cases(entries, rows):
    return [(index, args, entries[index](*args)) for index, args in rows]


def _rounding():
    def nearest(value, divisor):
        return int((Decimal(value) / divisor).to_integral_value(rounding=ROUND_HALF_UP))

    def offset(value):
        return max(-128, min(127, nearest(value, 1000)))

    def hysteresis(requested, sensor):
        register = nearest(requested - sensor * 1000, 1000)
        return register if 0 <= register <= 255 else -34

    oracle = nearest, offset, hysteresis
    return _task(
        'upstream_linux_round_closest', 'body', 'div_round_closest', 'value divisor',
        'Round value/divisor to the nearest integer for signed dividends, including negative values. '
        'Exact half-way cases round away from zero. Keep positive-dividend behavior. The divisor is positive '
        '(1..10000) and the dividend is between -1000000 and 1000000.',
        'https://github.com/torvalds/linux/commit/b6d86d3d6d6e4c9b588d81615c81b5a8292b62ed',
        'Signed DIV_ROUND_CLOSEST and two hardware-monitor register conversions. Drivers return their '
        'computed register or range-error code in this extraction.',
        ('''shifted = value + divisor // 2
return shifted // divisor if shifted >= 0 else -((-shifted) // divisor)''',
         'return (value + divisor / 2) / divisor;'),
        ('''magnitude = (abs(value) + divisor // 2) // divisor
return -magnitude if value < 0 else magnitude''',
         '''if value < 0 { return (value - divisor / 2) / divisor; }
return (value + divisor / 2) / divisor;'''),
        [('temp_offset_register', 'millidegrees',
          'return max(-128, min(127, div_round_closest(millidegrees, 1000)))',
          '''let r = div_round_closest(millidegrees, 1000);
if r < -128 { return -128; }
return if r > 127 { 127 } else { r };'''),
         ('hysteresis_register', 'requested sensor',
          '''r = div_round_closest(requested - sensor * 1000, 1000)
return r if 0 <= r <= 255 else -34''',
          '''let r = div_round_closest(requested - sensor * 1000, 1000);
return if r < 0 || r > 255 { -34 } else { r };''')],
        _cases(oracle, [(1, (-1500,)), (0, (5, 2)), (2, (20499, 20))]),
        _cases(oracle, [(0, (-2, 2)), (0, (-2, 3)), (0, (-1, 3)), (0, (0, 7)),
                        (0, (-5000, 10000)), (0, (-7, 1)), (0, (9, 2)), (0, (31, 9)),
                        (1, (-499,)), (1, (-500,)), (1, (-129000,)), (1, (126500,)), (1, (130000,)),
                        (2, (19500, 20)), (2, (19501, 20)), (2, (0, 0)), (2, (255499, 0)), (2, (255500, 0))]))


def _calendar():
    # Month overflow is bounded to at most one year in either direction.
    py_length = '''y = year
m = month
if m < 0:
    m += 12
    y -= 1
if m > 11:
    m -= 12
    y += 1
if m == 1:
    return 29 if y % 400 == 0 or (y % 4 == 0 and y % 100 != 0) else 28
return 31 - (m % 7) % 2'''
    scalar_length = '''var y = year;
var m = month;
if m < 0 { m += 12; y -= 1; }
if m > 11 { m -= 12; y += 1; }
if m == 1 { return if y % 400 == 0 || (y % 4 == 0 && y % 100 != 0) { 29 } else { 28 }; }
return 31 - (m % 7) % 2;'''
    py_old = py_length.replace('y = year', 'y = year + 1900 if 0 <= year <= 99 else year', 1)
    scalar_old = scalar_length.replace('var y = year;', 'var y = if year >= 0 && year <= 99 { year + 1900 } else { year };', 1)
    def days(year, month):
        carry, normalized = divmod(month, 12)
        return monthrange(year + carry, normalized + 1)[1]

    def overflow(year, month, day):
        if month not in range(12):
            return 1
        return -1 if 1 <= day <= days(year, month) else 2

    oracle = days, lambda y, m, d: min(d, days(y, m)), overflow
    return _task(
        'upstream_moment_month_length', 'body', 'days_in_month', 'year month',
        'Fix the Gregorian month length for early years, including leap-year February in year zero. '
        'Use the supplied astronomical year; JavaScript Date.UTC remaps years 0..99 into the 1900s. '
        'Months are zero-indexed: normalize overflow into the adjacent year before determining its length. '
        'Inputs are integers; years -400..2400 and months -12..23.',
        'https://github.com/moment/moment/commit/f5953bdf32bca2b48581f6058469008aed1de027',
        'Moment.js daysInMonth, the date clamp in setMonth, and the month/day component of checkOverflow.',
        (py_old, scalar_old), (py_length, scalar_length),
        [('set_month_day', 'year month day',
          'return min(day, days_in_month(year, month))',
          'let limit = days_in_month(year, month);\nreturn if day < limit { day } else { limit };'),
         ('check_overflow', 'year month day',
          '''if month < 0 or month > 11:
    return 1
return 2 if day < 1 or day > days_in_month(year, month) else -1''',
          '''if month < 0 || month > 11 { return 1; }
return if day < 1 || day > days_in_month(year, month) { 2 } else { -1 };''')],
        _cases(oracle, [(1, (0, 1, 31)), (0, (2000, 1)), (2, (99, 2, 31))]),
        _cases(oracle, [(0, (0, 1)), (0, (99, 13)), (0, (1, -11)), (0, (-400, 1)), (0, (1900, 1)),
                        (0, (0, 23)), (0, (2400, -12)), (0, (2001, 8)),
                        (1, (1, -11, 31)), (1, (99, 13, 29)), (1, (0, 1, 12)), (1, (2004, 3, 31)),
                        (2, (0, 1, 29)), (2, (0, 1, 30)), (2, (100, 1, 29)), (2, (2004, -1, 20)),
                        (2, (2004, 0, 0)), (2, (2004, 6, 31))]))


def _rectangles():
    spec = 'width height x y other_w other_h'
    args = 'width, height, x, y, other_w, other_h'
    def shared(width, height, x, y, other_w, other_h):
        first = {(a, b) for a in range(width) for b in range(height)}
        return {(a, b) for a in range(x, x + other_w) for b in range(y, y + other_h)} & first

    def span(*values):
        pixels = shared(*values)
        return len({x for x, _ in pixels}) + len({y for _, y in pixels})

    oracle = lambda *v: int(bool(shared(*v))), span, lambda *v: int(bool(shared(*v)))
    def predicate(equality):
        le = '<=' if equality else '<'
        ge = '>=' if equality else '>'
        return (f'return int(0 {le} x + other_w and width {ge} x and 0 {le} y + other_h and height {ge} y)',
                f'return if 0 {le} x + other_w && width {ge} x && 0 {le} y + other_h && height {ge} y {{ 1 }} else {{ 0 }};')
    return _task(
        'upstream_godot_rect_intersects', 'body', 'rect_intersects', spec,
        'Fix intersection of integer pixel rectangles: rectangles that only touch along an edge or corner '
        'do not intersect. Return 1 exactly when they share a pixel, else 0. The first rectangle begins at '
        '(0,0); the second at (x,y). All widths and heights are 1..20 and positions -30..30.',
        'https://github.com/godotengine/godot/commit/23a4fe5b27c191eae1dde05aa522463e67b0766f',
        'Godot Rect2i::intersects, scalar size projection of Rect2i::intersection, and the renderer copy gate.',
        predicate(True), predicate(False),
        [('intersection_span', spec,
          f'''if not rect_intersects({args}):
    return 0
return min(width, x + other_w) - max(0, x) + min(height, y + other_h) - max(0, y)''',
          f'''if rect_intersects({args}) == 0 {{ return 0; }}
let right = if width < x + other_w {{ width }} else {{ x + other_w }};
let bottom = if height < y + other_h {{ height }} else {{ y + other_h }};
let left = if x > 0 {{ x }} else {{ 0 }};
let top = if y > 0 {{ y }} else {{ 0 }};
return right - left + bottom - top;'''),
         ('copy_to_back_buffer', spec,
          f'return int(intersection_span({args}) != 0)',
          f'return if intersection_span({args}) != 0 {{ 1 }} else {{ 0 }};')],
        _cases(oracle, [(2, (5, 4, 5, 0, 3, 3)), (0, (8, 6, 7, 5, 2, 2)), (1, (3, 4, -2, 1, 4, 1))]),
        _cases(oracle, [(0, (6, 5, -2, 0, 2, 3)), (0, (6, 5, 0, -2, 2, 2)), (0, (6, 5, 3, 5, 3, 2)),
                        (0, (6, 5, 6, 5, 4, 4)), (0, (1, 1, 0, 0, 1, 1)), (0, (3, 3, -4, 0, 3, 3)),
                        (1, (3, 5, 0, 5, 2, 4)), (1, (6, 5, -2, -3, 7, 8)), (1, (8, 6, 2, 3, 1, 1)),
                        (1, (4, 8, 4, 2, 1, 4)), (1, (20, 20, 30, 30, 1, 1)),
                        (2, (8, 6, 2, -5, 4, 5)), (2, (5, 5, 9, 8, 2, 5)), (2, (8, 6, 7, 5, 1, 1)),
                        (2, (5, 4, 0, 0, 5, 4)), (2, (5, 4, 5, 4, 2, 2))]))


TASKS = [_rounding(), _calendar(), _rectangles()]
