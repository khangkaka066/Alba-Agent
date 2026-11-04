class ExpressionError(ValueError):
    """Raised for syntax errors and unknown names in an expression."""


def evaluate(expression: str, variables: dict[str, int | float] | None = None) -> int | float:
    raise NotImplementedError
