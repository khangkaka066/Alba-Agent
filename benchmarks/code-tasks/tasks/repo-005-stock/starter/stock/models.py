"""Inventory records."""


class OutOfStock(Exception):
    pass


class Item:
    """``qty`` units are owned; ``reserved`` of them are set aside for orders; ``available`` is what can still be reserved."""

    def __init__(self, sku, qty):
        self.sku = sku
        self.qty = qty
        self.reserved = 0

    @property
    def available(self):
        return self.qty - self.reserved
