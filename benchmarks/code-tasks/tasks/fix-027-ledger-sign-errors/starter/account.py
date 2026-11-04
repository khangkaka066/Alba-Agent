"""A bank account that books ledger entries."""

from ledger import Entry


class InsufficientFunds(Exception):
    """A withdrawal or outgoing transfer would take the balance below zero."""


class Account:
    """Keeps the list of entries; the balance is always the sum of their signed amounts.

    ``withdrawal`` and ``transfer_out`` entries are refused (InsufficientFunds, nothing
    booked) when they would make the balance negative. Fees are always booked, even if
    they push the balance below zero.
    """

    def __init__(self, owner):
        self.owner = owner
        self.entries = []

    def balance(self):
        return sum(entry.signed for entry in self.entries)

    def book(self, kind, cents):
        entry = Entry(kind, cents)
        if kind in ("withdrawal", "transfer_out") and self.balance() + entry.signed < 0:
            raise InsufficientFunds(f"{self.owner}: balance {self.balance()}, needs {cents}")
        self.entries.append(entry)
        return entry


def transfer(source, target, cents):
    """Move ``cents`` from ``source`` to ``target`` (nothing changes if funds are short)."""
    source.book("transfer_out", cents)
    target.book("transfer_in", cents)
