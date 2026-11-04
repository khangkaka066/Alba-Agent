"""Tokenizer for a tiny arithmetic language with inclusive integer ranges."""


class TokenError(Exception):
    """Raised for a character that is not part of the language."""


def tokenize(src):
    """Split ``src`` into a list of ``(kind, value)`` tokens.

    Kinds: ``"int"`` and ``"float"`` (value already converted), ``"op"`` (one of
    ``+ - * / ..``), ``"lparen"`` and ``"rparen"``. Whitespace is skipped.

    A number is a run of digits. It is a float only when the digits are followed by a
    single ``.`` and then at least one more digit (``1.5``). Two dots are the range
    operator, so ``1..5`` is the tokens int 1, op "..", int 5, and ``1.5..7`` is
    float 1.5, op "..", int 7.
    """
    tokens = []
    i = 0
    n = len(src)
    while i < n:
        ch = src[i]
        if ch.isspace():
            i += 1
        elif ch.isdigit():
            j = i
            while j < n and src[j].isdigit():
                j += 1
            if j + 1 < n and src[j] == "." and src[j + 1].isdigit():
                j += 1
                while j < n and src[j].isdigit():
                    j += 1
                tokens.append(("float", float(src[i:j])))
            else:
                tokens.append(("int", int(src[i:j])))
            i = j
        elif src.startswith("..", i):
            tokens.append(("op", ".."))
            i += 2
        elif ch in "+-*/":
            tokens.append(("op", ch))
            i += 1
        elif ch == "(":
            tokens.append(("lparen", ch))
            i += 1
        elif ch == ")":
            tokens.append(("rparen", ch))
            i += 1
        else:
            raise TokenError(f"unexpected character {ch!r} at {i}")
    return tokens
