"""A day schedule that refuses conflicting bookings."""

from intervals import Interval, merge, overlaps


class Conflict(Exception):
    """The requested interval overlaps an existing booking."""


class Schedule:
    def __init__(self):
        self._booked = {}

    def book(self, name, interval):
        """Book ``interval`` under ``name``. Raises Conflict if it overlaps any booking
        (sharing only a boundary is not an overlap) and ValueError if the
        name is already used."""
        if name in self._booked:
            raise ValueError(f"{name!r} is already booked")
        for other in self._booked.values():
            if overlaps(interval, other):
                raise Conflict(f"{interval} overlaps {other}")
        self._booked[name] = interval

    def cancel(self, name):
        """Remove a booking; returns its interval. Unknown names raise KeyError."""
        return self._booked.pop(name)

    def names(self):
        """Booking names ordered by start time."""
        return [n for n, _ in sorted(self._booked.items(), key=lambda item: item[1])]

    def free_slots(self, day_start, day_end, min_length=1):
        """Gaps inside ``[day_start, day_end)`` that are at least ``min_length`` minutes long.

        Returned as a sorted list of Interval. Bookings that stick out of the window are
        clipped to it; bookings entirely outside it are ignored.
        """
        window = Interval(day_start, day_end)
        busy = []
        for iv in self._booked.values():
            if overlaps(iv, window):
                busy.append(Interval(max(iv.start, day_start), min(iv.end, day_end)))
        free = []
        cursor = day_start
        for block in merge(busy):
            if block.start - cursor >= min_length:
                free.append(Interval(cursor, block.start))
            cursor = block.end
        if day_end - cursor >= min_length:
            free.append(Interval(cursor, day_end))
        return free
