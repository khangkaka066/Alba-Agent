def _check(*values: int) -> None:
    if any(v < 0 for v in values):
        raise ValueError("arguments must be >= 0")


def popcount(n: int) -> int:
    _check(n)
    return bin(n).count("1")


def is_power_of_two(n: int) -> bool:
    return n > 0 and n & (n - 1) == 0


def next_power_of_two(n: int) -> int:
    _check(n)
    return 1 if n <= 1 else 1 << (n - 1).bit_length()


def get_bit(n: int, i: int) -> int:
    _check(n, i)
    return (n >> i) & 1


def set_bit(n: int, i: int) -> int:
    _check(n, i)
    return n | (1 << i)


def clear_bit(n: int, i: int) -> int:
    _check(n, i)
    return n & ~(1 << i)


def toggle_bit(n: int, i: int) -> int:
    _check(n, i)
    return n ^ (1 << i)


def extract_bits(n: int, start: int, length: int) -> int:
    _check(n, start, length)
    return (n >> start) & ((1 << length) - 1)


def reverse_bits(n: int, width: int) -> int:
    _check(n, width)
    if width < 1 or n >= 1 << width:
        raise ValueError("n must fit in width bits and width must be >= 1")
    result = 0
    for _ in range(width):
        result = (result << 1) | (n & 1)
        n >>= 1
    return result


def lowest_set_bit(n: int) -> int:
    _check(n)
    return n & -n
