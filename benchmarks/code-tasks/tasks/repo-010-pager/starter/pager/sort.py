"""Sorting records."""


def sort_items(items, key, desc=False):
    """A new list of the items (dicts) ordered by ``item[key]``, ascending or, with ``desc``, descending.

    The sort is stable: items with equal values keep their original relative order in both directions. Items that do not
    have the key, or whose value is ``None``, come last whichever the direction, in their original order. Values of the
    items that have the key are assumed to be comparable with each other.
    """
    return sorted(items, key=lambda item: (item.get(key) is None, item.get(key)), reverse=desc)
