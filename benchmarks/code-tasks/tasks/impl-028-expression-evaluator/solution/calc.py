from __future__ import annotations

import re
from typing import Any, Mapping


class ExprError(ValueError):
    pass


class ExprSyntaxError(ExprError):
    pass


class UndefinedNameError(ExprError):
    pass


_TOKEN = re.compile(r"\s*(?:(\d+\.\d+|\d+)|([A-Za-z_][A-Za-z0-9_]*)|([-+*/%^(),]))")
_FUNCTIONS = {"abs": (1, 1), "min": (1, None), "max": (1, None)}


def _tokenize(text: str) -> list[tuple[str, str]]:
    tokens: list[tuple[str, str]] = []
    pos = 0
    while True:
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos >= len(text):
            return tokens
        m = _TOKEN.match(text, pos)
        if not m:
            raise ExprSyntaxError(f"illegal character at {pos}")
        pos = m.end()
        if m.group(1) is not None:
            tokens.append(("num", m.group(1)))
        elif m.group(2) is not None:
            tokens.append(("name", m.group(2)))
        else:
            tokens.append(("op", m.group(3)))


class _Parser:
    def __init__(self, tokens: list[tuple[str, str]]) -> None:
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> tuple[str, str] | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def accept(self, *ops: str) -> str | None:
        tok = self.peek()
        if tok and tok[0] == "op" and tok[1] in ops:
            self.pos += 1
            return tok[1]
        return None

    def expect(self, op: str) -> None:
        if not self.accept(op):
            raise ExprSyntaxError(f"expected {op!r}")

    def parse(self) -> Any:
        node = self.expr()
        if self.peek() is not None:
            raise ExprSyntaxError("unexpected trailing tokens")
        return node

    def expr(self) -> Any:
        node = self.term()
        while (op := self.accept("+", "-")):
            node = ("bin", op, node, self.term())
        return node

    def term(self) -> Any:
        node = self.unary()
        while (op := self.accept("*", "/", "%")):
            node = ("bin", op, node, self.unary())
        return node

    def unary(self) -> Any:
        if (op := self.accept("+", "-")):
            return ("neg" if op == "-" else "pos", self.unary())
        return self.power()

    def power(self) -> Any:
        base = self.atom()
        if self.accept("^"):
            return ("bin", "^", base, self.unary())
        return base

    def atom(self) -> Any:
        tok = self.peek()
        if tok is None:
            raise ExprSyntaxError("unexpected end of expression")
        kind, value = tok
        if kind == "num":
            self.pos += 1
            return ("num", float(value) if "." in value else int(value))
        if kind == "name":
            self.pos += 1
            if self.accept("("):
                args = []
                if not self.accept(")"):
                    args.append(self.expr())
                    while self.accept(","):
                        args.append(self.expr())
                    self.expect(")")
                if value in _FUNCTIONS:
                    low, high = _FUNCTIONS[value]
                    if len(args) < low or (high is not None and len(args) > high):
                        raise ExprSyntaxError(f"wrong number of arguments for {value}")
                return ("call", value, args)
            return ("var", value)
        if self.accept("("):
            node = self.expr()
            self.expect(")")
            return node
        raise ExprSyntaxError(f"unexpected token {value!r}")


def _eval(node: Any, variables: Mapping[str, float]) -> Any:
    kind = node[0]
    if kind == "num":
        return node[1]
    if kind == "var":
        if node[1] not in variables:
            raise UndefinedNameError(node[1])
        return variables[node[1]]
    if kind == "neg":
        return -_eval(node[1], variables)
    if kind == "pos":
        return _eval(node[1], variables)
    if kind == "call":
        args = [_eval(a, variables) for a in node[2]]
        if node[1] not in _FUNCTIONS:
            raise UndefinedNameError(node[1])
        if node[1] == "abs":
            return abs(args[0])
        return (min if node[1] == "min" else max)(args)
    _, op, left_node, right_node = node
    left = _eval(left_node, variables)
    right = _eval(right_node, variables)
    if op == "+":
        return left + right
    if op == "-":
        return left - right
    if op == "*":
        return left * right
    if op == "/":
        return left / right
    if op == "%":
        return left % right
    result = left ** right
    if isinstance(result, complex):
        raise ExprError("negative base with fractional exponent")
    return result


def evaluate(expression: str, variables: Mapping[str, float] | None = None) -> float:
    tree = _Parser(_tokenize(expression)).parse()
    return _eval(tree, variables or {})
