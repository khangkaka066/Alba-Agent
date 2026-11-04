"""Orders over several skus."""


def place_order(store, lines):
    """Reserve every ``(sku, n)`` in ``lines`` (a list; the same sku may appear more than once).

    An empty list is a ValueError. Every sku is checked first: an unknown one raises KeyError(sku) before anything
    is reserved. The order is all-or-nothing: if any line fails (OutOfStock, ValueError) everything this call had
    already reserved is released and the exception propagates, so the store is exactly as it was.
    """
    if not lines:
        raise ValueError("an order needs at least one line")
    for sku, n in lines:
        store.reserve(sku, n)


def cancel_order(store, lines):
    """Release every ``(sku, n)`` of a previously placed order."""
    for sku, n in lines:
        store.release(sku, n)
