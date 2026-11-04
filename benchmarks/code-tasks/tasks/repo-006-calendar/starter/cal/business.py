"""Working days (Monday to Friday)."""

import datetime

from .arith import add_days


def weekday(date):
    """0 for Monday ... 6 for Sunday."""
    return datetime.date(*date).weekday()


def business_days_between(start, end):
    """How many Monday-Friday days ``d`` satisfy ``start <= d < end``; 0 when ``end`` is not after ``start``."""
    count = 0
    current = start
    while current <= end:
        if weekday(current) < 5:
            count += 1
        current = add_days(current, 1)
    return count


def next_business_day(date):
    """The first Monday-Friday day strictly after ``date``."""
    current = add_days(date, 1)
    while weekday(current) >= 5:
        current = add_days(current, 1)
    return current
