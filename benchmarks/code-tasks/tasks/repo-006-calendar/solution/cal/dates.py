"""Calendar dates are ``(year, month, day)`` tuples of ints in the proleptic Gregorian calendar."""

import re

_ISO = re.compile(r"\d{4}-\d{2}-\d{2}")


def is_leap(year):
    """Gregorian rule: divisible by 4, except century years, which must be divisible by 400."""
    return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)


def days_in_month(year, month):
    """Number of days in the month; ValueError if ``month`` is not 1..12."""
    if not 1 <= month <= 12:
        raise ValueError("month must be 1..12")
    if month == 2:
        return 29 if is_leap(year) else 28
    return 30 if month in (4, 6, 9, 11) else 31


def parse_date(text):
    """Parse ``"YYYY-MM-DD"`` into ``(year, month, day)``.

    The text must be exactly four digits, a dash, two digits, a dash, two digits ("2024-2-5" and " 2024-02-05" are
    errors), the year must be at least 1 and the date must exist ("2023-02-29" does not). Anything else is a ValueError.
    """
    if not isinstance(text, str) or not _ISO.fullmatch(text) or not text.isascii():
        raise ValueError(f"not a date: {text!r}")
    year, month, day = (int(part) for part in text.split("-"))
    if year < 1 or not 1 <= month <= 12 or not 1 <= day <= days_in_month(year, month):
        raise ValueError(f"not a date: {text!r}")
    return (year, month, day)
