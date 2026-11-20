"""Frozen scalar transitions and specifications independent of the submitted expressions."""

from collections import deque
from dataclasses import dataclass
from itertools import product
from random import Random
from statistics import median_low


@dataclass(frozen=True)
class Task:
    name: str
    args: tuple
    result: str
    request: str
    old: str
    reference: str
    domains: tuple
    initial: int | bool | None = None
    events: tuple = ()


I, B = 'I64', 'Bool'
R = lambda a,b: tuple(range(a,b+1))
BITS = (False, True)
TASKS = (
    Task('drum_index', (('slot',I),('advance',I)), I,
         'Advance the read head clockwise on a five-slot drum. After slot four it continues from slot zero. Advances are nonnegative.',
         'slot + advance', '(slot + advance) % 5', (R(0,4),R(0,9)), 0, (1,2,4)),
    Task('bit_packet', (('prefix',I),('incoming',B)), I,
         'Append the incoming low bit to the nonnegative binary prefix. Retain every previous bit.',
         'prefix + int(incoming)', 'prefix * 2 + int(incoming)', (R(0,64),BITS), 0, BITS),
    Task('fan_memory', (('spinning',B),('reading',I)), B,
         'Start a stopped fan at readings of five or above. Stop a running fan at readings of two or below. A reading between those thresholds preserves its prior state.',
         'reading >= 5', 'reading > 2 if spinning else reading >= 5', (BITS,R(-2,9)), False, (1,3,4,6)),
    Task('camera_follow', (('location',I),('target',I)), I,
         'Move the camera by one integer position toward its target, or stay still if it is already there.',
         'target', 'max(location - 1, min(target, location + 1))', (R(-5,5),R(-6,6)), 0, (-3,0,2,4)),
    Task('time_intersection', (('start_a',I),('end_a',I),('start_b',I),('end_b',I)), B,
         'Decide if two integer tick ranges share at least one tick. Each includes its start and excludes its end. A reversed or zero-length range contains no ticks.',
         'start_a < end_b', 'max(start_a, start_b) < min(end_a, end_b)', (R(-1,3),)*4),
    Task('sensor_vote', (('left',I),('center',I),('right',I)), I,
         'Return the middle of three sensor readings by value, including ties. Ignore their order.',
         'center', 'max(min(left, center), min(max(left, center), right))', (R(-3,3),)*3),
    Task('meeting_quorum', (('present',I),('registered',I)), B,
         'A nonempty register reaches quorum once at least two thirds of its members are present. Counts are nonnegative and attendance cannot exceed registration.',
         'present * 2 >= registered', 'registered > 0 and 3 * present >= 2 * registered', (R(0,18),R(0,18))),
    Task('parcel_pick', (('ordered',I),('ready',I)), I,
         'Pick as many parcels from the ready pile as are ordered. Picking stops when either the order is full or the ready pile runs out. Both counts are nonnegative.',
         'ordered', 'min(ordered, ready)', (R(0,15),R(0,15))),
    Task('tile_color', (('column',I),('row',I)), B,
         'Return true on a dark checkerboard tile. The origin is light and every horizontal or vertical step changes color. Coordinates are nonnegative.',
         'column % 2 == 1', '(column + row) % 2 == 1', (R(0,12),R(0,12))),
)


def expected(t, args):
    if t.name == 'drum_index':
        head = deque(range(5))
        head.rotate(-args[0])
        for _ in range(args[1]):
            head.rotate(-1)
        return head[0]
    if t.name == 'bit_packet':
        return int(f'{args[0]:b}{int(args[1])}', 2)
    if t.name == 'fan_memory':
        return (['off']*5 + ['on']*5)[min(9,max(0,args[1]))] == 'on' if not args[0] else args[1] not in range(-100,3)
    if t.name == 'camera_follow':
        here, there = args
        if here == there:
            return here
        return list(range(here, there, 1 if here < there else -1))[1:2][0] if abs(there-here)>1 else there
    if t.name == 'time_intersection':
        a,b,c,d = args
        return bool(set(range(a,b)).intersection(range(c,d)))
    if t.name == 'sensor_vote':
        return median_low(args)
    if t.name == 'meeting_quorum':
        people, all_people = args
        # Find the first integer attendance reaching an exact rational threshold.
        threshold = next((n for n in range(all_people+1) if n*3 >= all_people*2), 0)
        return all_people != 0 and people in range(threshold,all_people+1)
    if t.name == 'parcel_pick':
        return len(list(zip(range(args[0]), range(args[1]))))
    if t.name == 'tile_color':
        color = False
        for axis in args:
            for _ in range(axis):
                color = not color
        return color
    raise KeyError(t.name)


def direct(t):
    return [x for x in product(*t.domains) if t.name != 'meeting_quorum' or x[0] <= x[1]]


def cases(t):
    domain = direct(t)
    shuffled = list(domain)
    Random(70429+TASKS.index(t)).shuffle(shuffled)
    # Boundary points plus a deterministic random sample. Give both result classes of predicates.
    chosen = [domain[0],domain[-1]]
    half = len(shuffled)//2
    if t.result == B:
        for label in (False,True):
            chosen.extend([p for p in shuffled if expected(t,p) is label][:6])
    for p in shuffled[:half]:
        if len(set(chosen)) >= 18:
            break
        chosen.append(p)
    public = list(dict.fromkeys(chosen))
    return public, [p for p in domain if p not in public]


def histories(t):
    return [list(seq) for n in range(2,7) for seq in product(t.events, repeat=n)] if t.events else []


def history_expected(t, events):
    if t.name == 'drum_index':
        return (sum(events) + t.initial) % 5
    if t.name == 'bit_packet':
        return int(''.join('1' if e else '0' for e in events),2)
    if t.name == 'fan_memory':
        decisive = [n for n in events if not 2 < n < 5]
        return bool(decisive and decisive[-1] >= 5)
    if t.name == 'camera_follow':
        point = t.initial
        for goal in events:
            point += (goal > point) - (goal < point)
        return point
    raise KeyError(t.name)
