"""Money helpers. Amounts are floats in currency units; internally we work in integer cents."""

from decimal import ROUND_HALF_UP, Decimal


def _half_away(value: Decimal) -> int:
    # ROUND_HALF_UP in decimal rounds ties away from zero.
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def to_cents(amount: float) -> int:
    """Convert a currency amount to integer cents, rounding half away from zero."""
    return _half_away(Decimal(repr(amount)) * 100)


def apply_rate(cents: int, rate: float) -> int:
    """Apply a fractional rate (e.g. 0.1 for 10%) to a cents amount, rounding half away from zero."""
    return _half_away(Decimal(cents) * Decimal(repr(rate)))


def format_cents(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    whole, frac = divmod(abs(cents), 100)
    return f"{sign}{whole}.{frac:02d}"
