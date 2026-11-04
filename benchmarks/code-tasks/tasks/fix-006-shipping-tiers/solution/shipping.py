"""Shipping fee calculation for the checkout service."""

# (maximum weight in kg, fee). Each tier covers weights up to AND INCLUDING its limit.
TIERS = [(1.0, 5.00), (5.0, 9.00), (20.0, 15.00)]

FREE_SHIPPING_MIN = 50.00


def parcel_fee(weight_kg):
    """Fee for a single parcel.

    A parcel of exactly 1.0 kg costs 5.00, anything above 1.0 and up to
    5.0 kg costs 9.00, and above 5.0 up to 20.0 kg costs 15.00.
    Weights <= 0 or above 20 kg raise ValueError.
    """
    if weight_kg <= 0:
        raise ValueError("weight must be positive")
    for limit, fee in TIERS:
        if weight_kg <= limit:
            return fee
    raise ValueError("parcel too heavy")


def order_shipping(parcel_weights, order_total):
    """Total shipping for an order made of several parcels.

    Orders whose total is 50.00 or more ship free (0.0). Otherwise the fee
    is the sum of every parcel's fee.
    """
    if order_total >= FREE_SHIPPING_MIN:
        return 0.0
    return sum(parcel_fee(w) for w in parcel_weights)
