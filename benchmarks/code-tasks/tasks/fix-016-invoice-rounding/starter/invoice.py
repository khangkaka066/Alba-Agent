"""Invoice arithmetic. All money is Decimal; amounts are rounded to cents."""

from decimal import Decimal

CENT = Decimal("0.01")


def to_cents(amount):
    """Round a Decimal to cents, rounding halves up: 0.125 -> 0.13, 2.675 -> 2.68."""
    return amount.quantize(CENT)


def line_total(unit_price, quantity):
    """Price of one invoice line. ``unit_price`` is a string such as "0.125"."""
    return to_cents(Decimal(unit_price) * quantity)


def invoice_total(lines, tax_rate):
    """Totals for ``lines`` = [(unit_price_str, quantity)] and a Decimal ``tax_rate``.

    Each line is rounded to cents first; subtotal is their sum; tax is the
    subtotal times the rate rounded to cents. Returns a dict with Decimal
    values for "subtotal", "tax" and "total".
    """
    subtotal = sum((line_total(price, qty) for price, qty in lines), Decimal("0.00"))
    tax = to_cents(subtotal * tax_rate)
    return {"subtotal": subtotal, "tax": tax, "total": subtotal + tax}


def split_evenly(amount, parties):
    """Split a cents-rounded Decimal ``amount`` between ``parties`` people.

    Every share is a whole number of cents and the shares add up to exactly
    ``amount``. When it does not divide evenly the leftover cents go one each
    to the first people, so Decimal("10.00") between 3 gives 3.34, 3.33, 3.33.
    """
    if parties < 1:
        raise ValueError("parties must be >= 1")
    cents = int(amount * 100)
    base = cents // parties
    return [Decimal(base).scaleb(-2) for _ in range(parties)]
