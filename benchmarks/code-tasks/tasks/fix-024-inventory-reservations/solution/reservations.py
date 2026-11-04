"""Order reservations on top of ``Stock``."""

from inventory import OutOfStock


class ReservationBook:
    """Tracks which order holds how many units of which SKU.

    * ``reserve`` holds units for an order; repeated reservations of the same SKU by the
      same order add up. It needs ``qty > 0`` (ValueError) and enough available stock
      (OutOfStock); on failure nothing changes.
    * ``reserve_many`` reserves several SKUs for an order all-or-nothing.
    * ``release`` gives back everything an order holds (unknown orders are ignored).
    * ``commit`` ships an order: the held units leave ``on_hand`` and stop being
      reserved, and the order no longer holds anything. Unknown orders raise KeyError.
    * ``held`` returns a copy of ``{sku: qty}`` held by an order (empty if none).
    """

    def __init__(self, stock):
        self.stock = stock
        self._holds = {}

    def reserve(self, order_id, sku, qty):
        if qty <= 0:
            raise ValueError("qty must be positive")
        if self.stock.available(sku) < qty:
            raise OutOfStock(f"{sku}: wanted {qty}, available {self.stock.available(sku)}")
        self.stock.reserved[sku] += qty
        holds = self._holds.setdefault(order_id, {})
        holds[sku] = holds.get(sku, 0) + qty

    def reserve_many(self, order_id, wanted):
        for sku, qty in wanted.items():
            if qty <= 0:
                raise ValueError("qty must be positive")
            if self.stock.available(sku) < qty:
                raise OutOfStock(f"{sku}: wanted {qty}, available {self.stock.available(sku)}")
        for sku, qty in wanted.items():
            self.reserve(order_id, sku, qty)

    def release(self, order_id):
        holds = self._holds.pop(order_id, {})
        for sku, qty in holds.items():
            self.stock.reserved[sku] -= qty

    def commit(self, order_id):
        holds = self._holds.pop(order_id)
        for sku, qty in holds.items():
            self.stock.on_hand[sku] -= qty
            self.stock.reserved[sku] -= qty

    def held(self, order_id):
        return dict(self._holds.get(order_id, {}))
