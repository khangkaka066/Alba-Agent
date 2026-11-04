"""Command-style front end: evaluate an expression and format the answer as text."""

from parser import ParseError, evaluate
from tokenizer import TokenError


def run(src):
    """Return the result of ``src`` as text, or ``"error: <reason>"`` for bad input.

    Ranges print as comma separated ints (``"1,2,3"``, empty range prints ``""``),
    ints print as ints and floats print with ``repr``.
    """
    try:
        value = evaluate(src)
    except (ParseError, TokenError) as exc:
        return f"error: {exc}"
    if isinstance(value, list):
        return ",".join(str(v) for v in value)
    return str(value) if isinstance(value, int) else repr(value)
