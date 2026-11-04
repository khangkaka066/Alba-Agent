"""Plain-text account statements."""

from .money import format_cents


def statement(account):
    """Return one line per history entry: "<day> <kind> <amount> <balance after>".

    Entries are ordered by day; entries of the same day keep the order in which they were
    recorded. ``amount`` is unsigned, ``balance after`` is the running balance in that printed
    order, starting from the opening balance (the current balance minus the net effect of all
    history entries). Both are formatted with ``format_cents``.
    """
    net = sum(c if kind == "deposit" else -c for kind, c, _ in account.history)
    running = account.balance - net
    rows = []
    for kind, cents, day in account.history:
        running += cents if kind == "deposit" else -cents
        rows.append((day, kind, cents, running))
    rows.sort(key=lambda row: row[0])
    return [f"{day} {kind} {format_cents(cents)} {format_cents(balance)}" for day, kind, cents, balance in rows]
