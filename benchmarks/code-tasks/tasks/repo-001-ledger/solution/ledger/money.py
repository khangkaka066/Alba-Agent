"""Money amounts are integer cents."""

from decimal import Decimal, InvalidOperation


def to_cents(text):
    """Parse a decimal string such as "12.34", "5", "-0.29" or "1,234.50" into integer cents.

    Thousands commas and surrounding whitespace are allowed. More than two decimal places,
    or text that is not a plain decimal number (including "nan" and "inf"), is a ValueError;
    nothing is ever rounded.
    """
    cleaned = text.replace(",", "").strip()
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        raise ValueError(f"not a number: {text!r}") from None
    if not value.is_finite():
        raise ValueError(f"not a number: {text!r}")
    cents = value * 100
    if cents != cents.to_integral_value():
        raise ValueError(f"more than two decimal places: {text!r}")
    return int(cents)


def format_cents(cents):
    """Format integer cents as "12,345.67"; negative amounts as "-0.05"."""
    sign = "-" if cents < 0 else ""
    whole, fraction = divmod(abs(cents), 100)
    return f"{sign}{whole:,}.{fraction:02d}"
