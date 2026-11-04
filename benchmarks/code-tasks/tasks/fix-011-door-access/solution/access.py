"""Door policy for the venue check-in desk."""

MIN_AGE = 18


def can_enter(age, has_ticket, is_vip):
    """Entry rule.

    A visitor must be at least 18 AND must either hold a ticket or be a VIP.
    Under-18s are never admitted, VIP or not.
    """
    return age >= MIN_AGE and (has_ticket or is_vip)


def admit(visitors):
    """Names admitted, in order.

    ``visitors`` is a list of dicts with keys name, age, ticket (bool), vip (bool).
    """
    return [v["name"] for v in visitors if can_enter(v["age"], v["ticket"], v["vip"])]


def door_summary(visitors):
    """Return (admitted_count, names_turned_away) for the list of visitors."""
    admitted = set(admit(visitors))
    turned_away = [v["name"] for v in visitors if v["name"] not in admitted]
    return len(admitted), turned_away
