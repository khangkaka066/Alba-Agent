"""Leaderboard ordering. An entry is a (name, score) tuple; higher score ranks first."""


def top(entries, n):
    """Return the best `n` entries, highest score first.

    Entries with equal scores keep their original (submission) order.
    """
    ordered = sorted(entries, key=lambda e: -e[1])
    return ordered[:n]
