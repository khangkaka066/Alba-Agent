"""Stock keeping for the warehouse dashboard."""


class Inventory:
    """Quantities and unit prices per SKU, with a cached total value."""

    def __init__(self):
        self._qty = {}
        self._price = {}
        self._total = None  # cached total_value(); None means "recompute"

    def add(self, sku, qty, unit_price):
        """Add ``qty`` units; the SKU's unit price becomes ``unit_price``."""
        self._qty[sku] = self._qty.get(sku, 0) + qty
        self._price[sku] = unit_price
        self._total = None

    def remove(self, sku, qty):
        """Remove ``qty`` units.

        Raises ValueError if the SKU is unknown or has fewer than ``qty`` units.
        A SKU whose quantity reaches 0 is dropped entirely, so it no longer
        counts in ``sku_count``.
        """
        have = self._qty.get(sku, 0)
        if qty > have:
            raise ValueError(f"not enough stock for {sku}")
        if qty == have:
            del self._qty[sku]
            del self._price[sku]
        else:
            self._qty[sku] = have - qty
        self._total = None

    def set_price(self, sku, unit_price):
        """Change the unit price of an existing SKU (KeyError if unknown)."""
        if sku not in self._price:
            raise KeyError(sku)
        self._price[sku] = unit_price
        self._total = None

    def total_value(self):
        """Sum of quantity * unit price over all SKUs, rounded to 2 places.

        Always reflects the current stock and prices.
        """
        if self._total is None:
            self._total = round(sum(q * self._price[s] for s, q in self._qty.items()), 2)
        return self._total

    def quantity(self, sku):
        """Units on hand (0 for an unknown SKU)."""
        return self._qty.get(sku, 0)

    def sku_count(self):
        """Number of distinct SKUs currently stocked."""
        return len(self._qty)
