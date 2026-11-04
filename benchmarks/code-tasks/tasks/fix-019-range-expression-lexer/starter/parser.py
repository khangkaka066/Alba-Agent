"""Recursive-descent evaluator for the tiny arithmetic language.

Grammar, lowest precedence first::

    range  := sum ( ".." sum )?
    sum    := term ( ("+" | "-") term )*
    term   := unary ( ("*" | "/") unary )*
    unary  := "-" unary | atom
    atom   := number | "(" range ")"

``a..b`` evaluates to the list of integers from ``a`` to ``b`` inclusive (empty when
``a > b``); both bounds must be ints. ``/`` is true division. Arithmetic on a range
result is not supported.
"""

from tokenizer import tokenize


class ParseError(Exception):
    """Raised for malformed input or a range with non-integer bounds."""


class _Parser:
    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else (None, None)

    def take(self):
        token = self.peek()
        self.pos += 1
        return token

    def at_op(self, *ops):
        kind, value = self.peek()
        return kind == "op" and value in ops

    def parse_range(self):
        start = self.parse_sum()
        if self.at_op(".."):
            self.take()
            end = self.parse_sum()
            if not (type(start) is int and type(end) is int):
                raise ParseError("range bounds must be integers")
            return list(range(start, end + 1))
        return start

    def parse_sum(self):
        value = self.parse_term()
        while self.at_op("+", "-"):
            _, op = self.take()
            rhs = self.parse_term()
            value = value + rhs if op == "+" else value - rhs
        return value

    def parse_term(self):
        value = self.parse_unary()
        while self.at_op("*", "/"):
            _, op = self.take()
            rhs = self.parse_unary()
            value = value * rhs if op == "*" else value / rhs
        return value

    def parse_unary(self):
        if self.at_op("-"):
            self.take()
            return -self.parse_unary()
        return self.parse_atom()

    def parse_atom(self):
        kind, value = self.take()
        if kind in ("int", "float"):
            return value
        if kind == "lparen":
            inner = self.parse_range()
            if self.take()[0] != "rparen":
                raise ParseError("expected ')'")
            return inner
        raise ParseError(f"unexpected token {value!r}")


def evaluate(src):
    """Evaluate ``src`` and return an int, a float or a list of ints."""
    parser = _Parser(tokenize(src))
    result = parser.parse_range()
    if parser.pos != len(parser.tokens):
        raise ParseError("unexpected trailing input")
    return result
