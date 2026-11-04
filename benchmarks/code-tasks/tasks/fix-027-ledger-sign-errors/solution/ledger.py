"""Ledger entry kinds and how they move money. Amounts are integer cents."""

# +1 adds to the balance, -1 subtracts from it.
SIGNS = {
    "deposit": 1,
    "interest": 1,
    "transfer_in": 1,
    "withdrawal": -1,
    "transfer_out": -1,
    "fee": -1,
}


class Entry:
    """One booked movement: ``kind`` (a key of SIGNS) and a positive ``cents`` amount."""

    def __init__(self, kind, cents):
        if kind not in SIGNS:
            raise ValueError(f"unknown entry kind: {kind!r}")
        if not isinstance(cents, int) or cents <= 0:
            raise ValueError("cents must be a positive int")
        self.kind = kind
        self.cents = cents

    @property
    def signed(self):
        """The amount with its sign: positive for money in, negative for money out."""
        return SIGNS[self.kind] * self.cents
