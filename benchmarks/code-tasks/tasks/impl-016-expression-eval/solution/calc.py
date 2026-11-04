import re


class ExpressionError(ValueError):
    """Raised for syntax errors and unknown names in an expression."""


_TOKEN = re.compile(
    r"\s*(?:(?P<num>[0-9]+(?:\.[0-9]+)?)|(?P<name>[A-Za-z_][A-Za-z0-9_]*)|(?P<op>\*\*|//|[-+*/%(),]))"
)
_FUNCTIONS = {
    "abs": (1, 1, lambda *a: abs(a[0])),
    "min": (1, None, lambda *a: min(a)),
    "max": (1, None, lambda *a: max(a)),
}


def _tokenize(text: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    pos = 0
    while True:
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos >= len(text):
            return tokens
        m = _TOKEN.match(text, pos)
        if m is None:
            raise ExpressionError(f"unexpected character {text[pos]!r}")
        kind = m.lastgroup or ""
        tokens.append((kind, m.group(kind)))
        pos = m.end()
        if kind == "num" and pos < len(text) and (text[pos] == "." or text[pos].isalnum() or text[pos] == "_"):
            raise ExpressionError("malformed number")


class _Parser:
    def __init__(self, tokens: list[tuple[str, str]], variables: dict[str, int | float]) -> None:
        self.tokens = tokens
        self.pos = 0
        self.variables = variables

    def peek(self) -> tuple[str, str] | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self) -> tuple[str, str]:
        token = self.peek()
        if token is None:
            raise ExpressionError("unexpected end of expression")
        self.pos += 1
        return token

    def accept(self, *ops: str) -> str | None:
        token = self.peek()
        if token is not None and token[0] == "op" and token[1] in ops:
            self.pos += 1
            return token[1]
        return None

    def parse(self) -> int | float:
        value = self.sum()
        if self.peek() is not None:
            raise ExpressionError(f"unexpected token {self.peek()[1]!r}")
        return value

    def sum(self):
        value = self.product()
        while (op := self.accept("+", "-")):
            right = self.product()
            value = value + right if op == "+" else value - right
        return value

    def product(self):
        value = self.unary()
        while (op := self.accept("*", "/", "//", "%")):
            right = self.unary()
            if op == "*":
                value = value * right
            elif op == "/":
                value = value / right
            elif op == "//":
                value = value // right
            else:
                value = value % right
        return value

    def unary(self):
        op = self.accept("+", "-")
        if op is None:
            return self.power()
        operand = self.unary()
        return -operand if op == "-" else +operand

    def power(self):
        base = self.primary()
        if self.accept("**"):
            return base ** self.unary()
        return base

    def primary(self):
        kind, text = self.take()
        if kind == "num":
            return float(text) if "." in text else int(text)
        if kind == "name":
            if self.accept("("):
                return self.call(text)
            if text not in self.variables:
                raise ExpressionError(f"unknown variable {text!r}")
            return self.variables[text]
        if text == "(":
            value = self.sum()
            if not self.accept(")"):
                raise ExpressionError("missing closing parenthesis")
            return value
        raise ExpressionError(f"unexpected token {text!r}")

    def call(self, name: str):
        if name not in _FUNCTIONS:
            raise ExpressionError(f"unknown function {name!r}")
        low, high, func = _FUNCTIONS[name]
        args = []
        if not self.accept(")"):
            args.append(self.sum())
            while self.accept(","):
                args.append(self.sum())
            if not self.accept(")"):
                raise ExpressionError("missing closing parenthesis")
        if len(args) < low or (high is not None and len(args) > high):
            raise ExpressionError(f"wrong number of arguments for {name}")
        return func(*args)


def evaluate(expression: str, variables: dict[str, int | float] | None = None) -> int | float:
    tokens = _tokenize(expression)
    if not tokens:
        raise ExpressionError("empty expression")
    return _Parser(tokens, variables or {}).parse()
