from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation

_CENT = Decimal("0.01")
_HUNDRED = Decimal(100)


def _round(value: Decimal) -> Decimal:
    return value.quantize(_CENT, rounding=ROUND_HALF_EVEN)


def _decimal(text: object) -> Decimal:
    if not isinstance(text, str):
        raise ValueError(f"expected a decimal string, got {text!r}")
    try:
        value = Decimal(text.strip())
    except InvalidOperation:
        raise ValueError(f"not a decimal: {text!r}") from None
    if not value.is_finite():
        raise ValueError(f"not a finite decimal: {text!r}")
    return value


def _percent(text: object) -> Decimal:
    value = _decimal(text)
    if value < 0 or value > 100:
        raise ValueError(f"percent out of range: {text!r}")
    return value


def price_order(
    items: list[tuple[str, int]], tax_percent: str, coupon_percent: str | None = None
) -> dict[str, str]:
    if items is None or tax_percent is None:
        raise TypeError("items and tax_percent are required")
    tax_rate = _percent(tax_percent)
    coupon_rate = None if coupon_percent is None else _percent(coupon_percent)
    subtotal = discount = tax = Decimal("0.00")
    for unit_price, qty in items:
        price = _decimal(unit_price)
        if price < 0:
            raise ValueError("negative price")
        if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
            raise ValueError(f"bad quantity: {qty!r}")
        line = _round(price * qty)
        line_discount = Decimal("0.00") if coupon_rate is None else _round(line * coupon_rate / _HUNDRED)
        line_tax = _round((line - line_discount) * tax_rate / _HUNDRED)
        subtotal += line
        discount += line_discount
        tax += line_tax
    total = subtotal - discount + tax
    return {
        "subtotal": f"{subtotal:.2f}",
        "discount": f"{discount:.2f}",
        "tax": f"{tax:.2f}",
        "total": f"{total:.2f}",
    }
