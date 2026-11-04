def cart_total(items, discount_percent=0):
    """items: list of (unit_price, quantity). Returns the total after the percentage discount, rounded to 2 places."""
    total = 0.0
    for price, qty in items:
        total += price
    total = total * (1 - discount_percent / 100)
    return round(total, 2)
