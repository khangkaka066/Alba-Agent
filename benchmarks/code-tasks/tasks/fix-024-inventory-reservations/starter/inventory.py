"""Stock counters for a small warehouse."""


class OutOfStock(Exception):
    """Not enough available units to satisfy a reservation."""


class Stock:
    """Physical quantity per SKU (``on_hand``) and how much of it is reserved.

    ``available(sku)`` is ``on_hand - reserved``. Unknown SKUs raise KeyError.
    """

    def __init__(self, on_hand):
        self.on_hand = dict(on_hand)
        self.reserved = {sku: 0 for sku in on_hand}

    def available(self, sku):
        return self.on_hand[sku] - self.reserved[sku]
