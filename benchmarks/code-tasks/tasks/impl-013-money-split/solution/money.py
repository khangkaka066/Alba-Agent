import re

_AMOUNT = re.compile(r"([+-]?)([0-9]+)(?:\.([0-9]+))?")


def to_cents(amount: str) -> int:
    m = _AMOUNT.fullmatch(amount)
    if m is None:
        raise ValueError(f"invalid amount: {amount!r}")
    sign, whole, frac = m.group(1), m.group(2), m.group(3) or ""
    padded = (frac + "00")[:2]
    cents = int(whole) * 100 + int(padded)
    if len(frac) > 2 and frac[2] >= "5":
        cents += 1
    return -cents if sign == "-" else cents


def format_cents(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    whole, frac = divmod(abs(cents), 100)
    return f"{sign}{whole}.{frac:02d}"


def allocate(total_cents: int, weights: list[int]) -> list[int]:
    if total_cents < 0:
        raise ValueError("total must be >= 0")
    if not weights:
        raise ValueError("weights must not be empty")
    if any(w < 0 for w in weights):
        raise ValueError("weights must be >= 0")
    denominator = sum(weights)
    if denominator == 0:
        raise ValueError("weights must not all be zero")
    shares = [total_cents * w // denominator for w in weights]
    remainders = [total_cents * w % denominator for w in weights]
    leftover = total_cents - sum(shares)
    order = sorted(range(len(weights)), key=lambda i: (-remainders[i], i))
    for i in order[:leftover]:
        shares[i] += 1
    return shares
