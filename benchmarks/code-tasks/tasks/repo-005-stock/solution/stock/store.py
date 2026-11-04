"""The inventory store."""

from .models import Item, OutOfStock


class Store:
    def __init__(self):
        self.items = {}

    def add_item(self, sku, qty):
        """Register ``qty`` units of ``sku``. ``qty`` must be an int >= 0, otherwise ValueError.

        Adding a sku that already exists adds ``qty`` to its quantity.
        """
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 0:
            raise ValueError("qty must be an int >= 0")
        if sku in self.items:
            self.items[sku].qty += qty
        else:
            self.items[sku] = Item(sku, qty)

    def get(self, sku):
        """The Item for ``sku``; KeyError(sku) if it is unknown."""
        if sku not in self.items:
            raise KeyError(sku)
        return self.items[sku]

    def reserve(self, sku, n):
        """Set aside ``n`` units. ``n`` must be an int >= 1 (else ValueError); an unknown sku is a KeyError;
        OutOfStock if ``n`` is more than the item's ``available`` units. Nothing changes when it raises."""
        if not isinstance(n, int) or isinstance(n, bool) or n < 1:
            raise ValueError("n must be an int >= 1")
        item = self.get(sku)
        if n > item.available:
            raise OutOfStock(sku)
        item.reserved += n

    def release(self, sku, n):
        """Give back ``n`` reserved units. ``n`` must be an int >= 1 and at most the item's ``reserved``
        units, otherwise ValueError. Nothing changes when it raises."""
        if not isinstance(n, int) or isinstance(n, bool) or n < 1:
            raise ValueError("n must be an int >= 1")
        item = self.get(sku)
        if n > item.reserved:
            raise ValueError("cannot release more than is reserved")
        item.reserved -= n

    def commit(self, sku, n):
        """Consume ``n`` reserved units: both ``qty`` and ``reserved`` drop by ``n``. ValueError if ``n`` is not an
        int >= 1 or is more than ``reserved``. Nothing changes when it raises."""
        if not isinstance(n, int) or isinstance(n, bool) or n < 1:
            raise ValueError("n must be an int >= 1")
        item = self.get(sku)
        if n > item.reserved:
            raise ValueError("cannot commit more than is reserved")
        item.qty -= n
        item.reserved -= n
