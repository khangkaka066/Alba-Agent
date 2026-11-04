"""Invoice totals built on money.py. Negative prices are refunds."""

from money import apply_rate, format_cents, to_cents


def line_cents(price: float, qty: int) -> int:
    return to_cents(price * qty)


def invoice_total(lines: list[tuple[float, int]], tax_rate: float = 0.0) -> int:
    subtotal = sum(line_cents(price, qty) for price, qty in lines)
    return subtotal + apply_rate(subtotal, tax_rate)


def render_total(lines: list[tuple[float, int]], tax_rate: float = 0.0) -> str:
    return format_cents(invoice_total(lines, tax_rate))
