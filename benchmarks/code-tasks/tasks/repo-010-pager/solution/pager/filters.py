"""Filtering records."""


def _matches(item, key, wanted):
    if key not in item:
        return False
    if isinstance(wanted, (list, tuple, set)):
        return item[key] in wanted
    return item[key] == wanted


def apply_filters(items, filters):
    """The items (dicts) that match every entry of ``filters`` (a dict), in their original order, as a new list.

    An entry whose value is a list, tuple or set matches when the item's value for that key is one of its members; any
    other value matches when the item's value equals it. An item that does not have the key never matches that entry,
    not even when the wanted value is ``None``. No filters means every item.
    """
    return [item for item in items if all(_matches(item, key, wanted) for key, wanted in filters.items())]
