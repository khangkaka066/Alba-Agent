"""Showing dates to people."""

from .business import weekday

_DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def human(date):
    """``"Thu 29 Feb 2024"``: weekday abbreviation, day without a leading zero, month abbreviation, year."""
    year, month, day = date
    return f"{_DAYS[weekday(date)]} {day:02d} {_MONTHS[month - 1]} {year}"
