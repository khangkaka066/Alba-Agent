"""Money helpers. Amounts are floats in currency units; internally we work in integer cents."""


def to_cents(amount: float) -> int:
    """Convert a currency amount to integer cents, rounding half away from zero."""
    return round(amount * 100)


def apply_rate(cents: int, rate: float) -> int:
    """Apply a fractional rate (e.g. 0.1 for 10%) to a cents amount, rounding half away from zero."""
    return round(cents * rate)


def format_cents(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    whole, frac = divmod(abs(cents), 100)
    return f"{sign}{whole}.{frac:02d}"
