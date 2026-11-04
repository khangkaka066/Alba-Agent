"""Order fulfilment checks against warehouse stock."""


def shortages(order, stock):
    """Return {sku: shortfall} for every sku in the order that stock cannot cover.

    ``order`` maps sku -> quantity wanted, ``stock`` maps sku -> quantity on hand
    (a sku missing from stock has 0 on hand). Every short sku is reported, not
    just the first. An empty dict means the order can be filled completely.
    """
    short = {}
    for sku, wanted in order.items():
        have = stock.get(sku, 0)
        if have >= wanted:
            continue
        short[sku] = wanted - have
    return short


def ship_now(order, stock):
    """Quantities that can be shipped immediately, as {sku: qty}.

    For each sku that is the smaller of the wanted and on-hand quantity; skus
    with nothing to ship are left out.
    """
    short = shortages(order, stock)
    result = {}
    for sku, wanted in order.items():
        ship = wanted - short.get(sku, 0)
        if ship > 0:
            result[sku] = ship
    return result


def can_fulfil(order, stock):
    """True if the whole order can be shipped from stock."""
    return not shortages(order, stock)
