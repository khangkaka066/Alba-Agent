"""Moving along the calendar."""

from .dates import days_in_month


def add_days(date, n):
    """The date ``n`` days after ``date`` (``n`` may be negative or large). ValueError when the result would be
    before year 1 or after year 9999."""
    year, month, day = date
    while n > 0:
        day += 1
        if day > days_in_month(year, month):
            day = 1
            month += 1
            if month > 12:
                month = 1
                year += 1
        n -= 1
    if not 1 <= year <= 9999:
        raise ValueError("date out of range")
    return (year, month, day)
