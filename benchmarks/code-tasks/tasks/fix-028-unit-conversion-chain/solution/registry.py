"""Known relations between measurement units."""


class UnitRegistry:
    """Stores direct relations ``1 <a> = <factor> <b>`` and answers which units are adjacent.

    ``add("km", "m", 1000)`` means 1 km = 1000 m; it also makes the reverse relation
    available, 1 m = 1/1000 km. Factors must be positive.
    """

    def __init__(self):
        self._edges = {}

    def add(self, a, b, factor):
        if factor <= 0:
            raise ValueError("factor must be positive")
        self._edges.setdefault(a, {})[b] = factor
        self._edges.setdefault(b, {})[a] = 1 / factor

    def __contains__(self, unit):
        return unit in self._edges

    def neighbours(self, unit):
        """List of ``(other_unit, factor)`` with ``1 unit = factor other_unit``, in the order added."""
        return list(self._edges[unit].items())
