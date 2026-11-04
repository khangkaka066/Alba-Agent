"""Room booking helpers. A stay runs from check_in (inclusive) to check_out (exclusive)."""

from datetime import timedelta


def nights(check_in, check_out):
    """Number of nights stayed (the check-out day itself is not a night).

    Raises ValueError unless check_out is after check_in.
    """
    if check_out <= check_in:
        raise ValueError("check_out must be after check_in")
    return (check_out - check_in).days


def occupied_dates(check_in, check_out):
    """Set of dates on which the room is occupied overnight.

    That is every date from check_in up to, but not including, check_out.
    """
    return {check_in + timedelta(days=i) for i in range(nights(check_in, check_out))}


def has_conflict(bookings, check_in, check_out):
    """True if the requested stay shares a night with any existing booking.

    ``bookings`` is a list of (check_in, check_out) dates. A guest may check in
    on the day another guest checks out.
    """
    wanted = occupied_dates(check_in, check_out)
    return any(wanted & occupied_dates(a, b) for a, b in bookings)


def free_dates(bookings, start, end):
    """Sorted list of dates in [start, end) with no booking overnight."""
    taken = set()
    for a, b in bookings:
        taken |= occupied_dates(a, b)
    days = (end - start).days
    return [start + timedelta(days=i) for i in range(days) if start + timedelta(days=i) not in taken]
