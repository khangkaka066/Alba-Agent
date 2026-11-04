"""Moving along the calendar."""

import datetime


def add_days(date, n):
    """The date ``n`` days after ``date`` (``n`` may be negative or large). ValueError when the result would be
    before year 1 or after year 9999."""
    try:
        moved = datetime.date(*date) + datetime.timedelta(days=n)
    except OverflowError:
        raise ValueError("date out of range") from None
    return (moved.year, moved.month, moved.day)
