"""Write rows of values as CSV text."""

from fields import format_field


def format_row(values, delimiter=","):
    """Join the formatted fields of one row with ``delimiter`` (no line terminator)."""
    return delimiter.join(format_field(v, delimiter) for v in values)


def write_table(header, rows, delimiter=","):
    """Return the CSV text: the header row then every data row, each ending in ``"\\r\\n"``.

    Every row must have as many values as the header, otherwise ValueError is raised.
    """
    lines = [format_row(header, delimiter)]
    for row in rows:
        if len(row) != len(header):
            raise ValueError(f"row has {len(row)} values, expected {len(header)}")
        lines.append(format_row(row, delimiter))
    return "".join(line + "\r\n" for line in lines)
