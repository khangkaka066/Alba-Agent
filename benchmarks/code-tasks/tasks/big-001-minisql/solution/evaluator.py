from errors import SqlError


def _value(operand, row):
    kind, value = operand
    if kind == "lit":
        return value
    if value not in row:
        raise SqlError(f"unknown column {value}")
    return row[value]


def evaluate(expr, row):
    kind = expr[0]
    if kind == "cmp":
        _, op, left, right = expr
        a, b = _value(left, row), _value(right, row)
        if a is None or b is None:
            return None
        if isinstance(a, str) != isinstance(b, str):
            raise SqlError("cannot compare text with a number")
        return {"=": a == b, "!=": a != b, "<": a < b, "<=": a <= b, ">": a > b, ">=": a >= b}[op]
    if kind == "and":
        a, b = evaluate(expr[1], row), evaluate(expr[2], row)
        if a is False or b is False:
            return False
        return None if a is None or b is None else True
    if kind == "or":
        a, b = evaluate(expr[1], row), evaluate(expr[2], row)
        if a is True or b is True:
            return True
        return None if a is None or b is None else False
    if kind == "not":
        inner = evaluate(expr[1], row)
        return None if inner is None else not inner
    if kind == "isnull":
        missing = _value(expr[1], row) is None
        return (not missing) if expr[2] else missing
    raise SqlError(f"unknown expression {kind}")


def matches(expr, row):
    return True if expr is None else evaluate(expr, row) is True
