from __future__ import annotations


def price_order(
    items: list[tuple[str, int]], tax_percent: str, coupon_percent: str | None = None
) -> dict[str, str]:
    raise NotImplementedError
