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
    lines = []
    for kind, cents, day in sorted(account.history, key=lambda entry: entry[2]):
        running += cents if kind == "deposit" else -cents
        lines.append(f"{day} {kind} {format_cents(cents)} {format_cents(running)}")
    return lines
