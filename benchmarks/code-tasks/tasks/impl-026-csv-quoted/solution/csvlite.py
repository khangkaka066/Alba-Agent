from __future__ import annotations


def _check_delimiter(delimiter: str) -> None:
    if not isinstance(delimiter, str) or len(delimiter) != 1 or delimiter in '"\n\r':
        raise ValueError("delimiter must be a single character other than quote or newline")


def parse_csv(text: str, delimiter: str = ",") -> list[list[str]]:
    _check_delimiter(delimiter)
    rows: list[list[str]] = []
    n = len(text)
    i = 0

    def at_terminator(pos: int) -> bool:
        return pos < n and (text[pos] == "\n" or text.startswith("\r\n", pos))

    while i < n:
        if text[i] == "\n":
            i += 1
            continue
        if text.startswith("\r\n", i):
            i += 2
            continue
        row: list[str] = []
        while True:
            if i < n and text[i] == '"':
                i += 1
                buf: list[str] = []
                while True:
                    if i >= n:
                        raise ValueError("unterminated quoted field")
                    c = text[i]
                    if c == '"':
                        if i + 1 < n and text[i + 1] == '"':
                            buf.append('"')
                            i += 2
                            continue
                        i += 1
                        break
                    buf.append(c)
                    i += 1
                row.append("".join(buf))
                if i < n and text[i] != delimiter and not at_terminator(i):
                    raise ValueError("unexpected character after closing quote")
            else:
                j = i
                while j < n and text[j] != delimiter and not at_terminator(j):
                    j += 1
                row.append(text[i:j])
                i = j
            if i < n and text[i] == delimiter:
                i += 1
                continue
            if i < n:
                i += 1 if text[i] == "\n" else 2
            break
        rows.append(row)
    return rows


def to_csv(rows: list[list[str]], delimiter: str = ",") -> str:
    _check_delimiter(delimiter)
    lines: list[str] = []
    for row in rows:
        if not row:
            raise ValueError("rows must not be empty")
        cells: list[str] = []
        for field in row:
            if not isinstance(field, str):
                raise TypeError("fields must be strings")
            needs_quotes = any(c in field for c in (delimiter, '"', "\n", "\r")) or (field == "" and len(row) == 1)
            cells.append('"' + field.replace('"', '""') + '"' if needs_quotes else field)
        lines.append(delimiter.join(cells) + "\n")
    return "".join(lines)
