"""Account statements."""


def format_cents(cents):
    """``12345`` -> ``"123.45"``; negative amounts get a leading minus: ``-5`` -> ``"-0.05"``."""
    sign = "-" if cents < 0 else ""
    whole, frac = divmod(abs(cents), 100)
    return f"{sign}{whole}.{frac:02d}"


def statement(account):
    """One ``(kind, signed_amount, running_balance)`` tuple per entry, oldest first."""
    rows = []
    running = 0
    for entry in account.entries:
        running += entry.signed
        rows.append((entry.kind, entry.signed, running))
    return rows


def render(account):
    """Text statement: one line per entry plus a final balance line."""
    lines = [
        f"{kind:<12}{format_cents(amount):>10}{format_cents(balance):>10}"
        for kind, amount, balance in statement(account)
    ]
    lines.append(f"{'balance':<12}{'':>10}{format_cents(account.balance()):>10}")
    return "\n".join(lines)
