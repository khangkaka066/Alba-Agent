from __future__ import annotations


def runs(text: str) -> list[tuple[str, int]]:
    result: list[tuple[str, int]] = []
    for ch in text:
        if result and result[-1][0] == ch:
            result[-1] = (ch, result[-1][1] + 1)
        else:
            result.append((ch, 1))
    return result


def encode(text: str) -> str:
    parts: list[str] = []
    for ch, count in runs(text):
        if ch.isascii() and ch.isdigit() or ch == "\\":
            ch = "\\" + ch
        parts.append(f"{count}{ch}")
    return "".join(parts)


def decode(data: str, max_length: int | None = None) -> str:
    parsed: list[tuple[str, int]] = []
    total = 0
    i, n = 0, len(data)
    while i < n:
        j = i
        while j < n and data[j] in "0123456789":
            j += 1
        digits = data[i:j]
        if not digits or digits[0] == "0":
            raise ValueError("run must start with a positive count without leading zeros")
        if j >= n:
            raise ValueError("count without a character")
        ch = data[j]
        if ch == "\\":
            if j + 1 >= n or data[j + 1] not in "0123456789\\":
                raise ValueError("invalid escape")
            ch = data[j + 1]
            j += 1
        count = int(digits)
        total += count
        if max_length is not None and total > max_length:
            raise ValueError("decoded length exceeds max_length")
        parsed.append((ch, count))
        i = j + 1
    return "".join(ch * count for ch, count in parsed)
