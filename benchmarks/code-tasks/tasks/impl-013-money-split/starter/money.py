def to_cents(amount: str) -> int:
    raise NotImplementedError


def format_cents(cents: int) -> str:
    raise NotImplementedError


def allocate(total_cents: int, weights: list[int]) -> list[int]:
    raise NotImplementedError
