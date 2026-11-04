"""Reports."""


def low_stock(store, threshold):
    """Sorted list of the skus whose ``available`` units are at or below ``threshold``."""
    return sorted(sku for sku, item in store.items.items() if item.available <= threshold)


def summary(store):
    """One line per sku, ordered by sku: ``"<sku> <qty> <reserved> <available>"``."""
    return [f"{sku} {item.qty} {item.reserved} {item.available}" for sku, item in sorted(store.items.items())]
