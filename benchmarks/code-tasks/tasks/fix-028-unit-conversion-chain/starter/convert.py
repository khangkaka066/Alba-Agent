"""Convert values between units by chaining registry relations."""

from collections import deque

from registry import UnitRegistry


class UnknownUnit(KeyError):
    """A unit is not in the registry."""


class NoConversion(Exception):
    """Both units are known but no chain of relations connects them."""


def default_registry():
    reg = UnitRegistry()
    reg.add("km", "m", 1000)
    reg.add("m", "cm", 100)
    reg.add("cm", "mm", 10)
    reg.add("in", "cm", 2.54)
    reg.add("ft", "in", 12)
    reg.add("yd", "ft", 3)
    reg.add("mi", "ft", 5280)
    reg.add("kg", "g", 1000)
    reg.add("lb", "oz", 16)
    return reg


def factor(registry, src, dst):
    """Multiplier such that ``1 src = factor dst``.

    Relations are chained along the path with the fewest steps (first found in
    registration order when several are equally short). ``src == dst`` gives 1.
    Raises UnknownUnit for a unit that is not registered and NoConversion when the
    units are unrelated (for example ``"kg"`` and ``"m"``).
    """
    for unit in (src, dst):
        if unit not in registry:
            raise UnknownUnit(unit)
    best = {src: 1.0}
    queue = deque([src])
    while queue:
        unit = queue.popleft()
        if unit == dst:
            return best[unit]
        for other, step in registry.neighbours(unit):
            if other not in best:
                best[other] = best[unit] * step
                queue.append(other)
    raise NoConversion(f"{src} -> {dst}")


def convert(registry, value, src, dst):
    return value * factor(registry, src, dst)
