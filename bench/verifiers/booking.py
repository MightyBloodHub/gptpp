"""Cancellation projection with the GPT++ component's checked-I64 boundary."""
from enum import Enum


class Booking(Enum):
    UNSEEN = 0
    ACTIVE = 1
    CANCELLED = 2


class Outcome(Enum):
    OK = 0
    UNKNOWN = 1


MAX = 2**63 - 1
Change = tuple[int, Booking, Outcome]


def plus_one(n: int) -> int:
    if n == MAX:
        raise OverflowError
    return n + 1


def cancel(n: int, state: Booking) -> Change:
    if state == Booking.ACTIVE:
        return plus_one(n), Booking.CANCELLED, Outcome.OK
    if state == Booking.CANCELLED:
        return n, Booking.CANCELLED, Outcome.OK
    return n, Booking.UNSEEN, Outcome.UNKNOWN


def active_cancel_twice(n: int) -> bool:
    """
    pre: 0 <= n < MAX
    post: __return__
    """
    first = cancel(n, Booking.ACTIVE)
    second = cancel(first[0], first[1])
    return first == (n + 1, Booking.CANCELLED, Outcome.OK) and second == first


def repeat_cancel(n: int) -> bool:
    """
    pre: 0 <= n <= MAX
    post: __return__
    """
    return cancel(n, Booking.CANCELLED) == (n, Booking.CANCELLED, Outcome.OK)


def unknown_cancel(n: int) -> bool:
    """
    pre: 0 <= n <= MAX
    post: __return__
    """
    return cancel(n, Booking.UNSEEN) == (n, Booking.UNSEEN, Outcome.UNKNOWN)
