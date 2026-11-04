"""CSV field formatting."""


def to_text(value):
    """None becomes the empty string, booleans become ``true``/``false``, everything else ``str(value)``."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def needs_quotes(text, delimiter=","):
    """True when ``text`` must be wrapped in double quotes.

    That is the case when it contains the delimiter, a double quote, a carriage return or a
    line feed, or when it starts or ends with a space.
    """
    return (
        delimiter in text
        or '"' in text
        or "\n" in text
        or "\r" in text
        or text.startswith(" ")
        or text.endswith(" ")
    )


def format_field(value, delimiter=","):
    """Return the field ready to be placed in a row: quoted if needed, with every inner
    double quote doubled."""
    text = to_text(value)
    if needs_quotes(text, delimiter):
        return '"' + text.replace('"', '""') + '"'
    return text
