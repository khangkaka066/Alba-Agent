"""Ordering rules for leaderboard entries."""


def sort_key(item):
    """Entries are ordered by ``score`` descending, ties broken by ``id`` ascending."""
    return (-item["score"], item["id"])


def sort_items(items):
    return sorted(items, key=sort_key)
