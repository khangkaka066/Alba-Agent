Implement `evaluate` in `calc.py` together with the provided `ExpressionError`.

`evaluate(expression: str, variables: dict[str, int | float] | None = None) -> int | float` parses and evaluates an arithmetic expression. Do not use `eval`, `exec`, `ast` or similar; write a tokenizer and a parser.

Syntax
- Numbers: `123` (an int) or `1.5` (a float): digits, optionally followed by `.` and one or more digits. `.5` and `5.` are invalid.
- Names: `[A-Za-z_][A-Za-z0-9_]*`. A name not followed by `(` is a variable looked up in `variables` (default: empty).
- Operators, from lowest to highest precedence:
  1. binary `+` `-` (left associative)
  2. binary `*` `/` `//` `%` (left associative)
  3. unary `+` `-` (prefix, may be repeated: `--3` is `3`)
  4. `**` (right associative): `2 ** 3 ** 2` is `2 ** 9 = 512`. Its left operand is a primary (number, variable, call, or parenthesised expression) and its right operand may itself carry a unary sign, so `2 ** -1` is `0.5`. Because `**` binds tighter than unary minus, `-2 ** 2` is `-4`.
- Parentheses `( ... )` group.
- Function calls `name(arg, arg, ...)` for exactly these functions: `abs` (exactly 1 argument), `min` and `max` (at least 1 argument). Arguments are full expressions separated by commas.
- Whitespace between tokens is ignored.

Semantics
- Arithmetic follows Python for ints and floats: `7 / 2` is `3.5`, `7 // 2` is `3`, `-7 // 2` is `-4`, `-7 % 3` is `2`, `2 ** 10` is the int `1024`, results of int-only `+ - * // % **` (with a non-negative exponent) are ints.
- Division, floor division or modulo by zero raises `ZeroDivisionError` (let Python raise it).
- Raise `ExpressionError` (a `ValueError` subclass, already defined in the stub) for: an empty or whitespace-only expression, an unexpected character, a malformed number (`.5`, `5.`, `1.2.3`, `12abc`), unbalanced parentheses, a missing operand or leftover tokens (`"1 2"`, `"3 +"`, `"* 3"`), an unknown variable name, an unknown function name, and a call with the wrong number of arguments (including `min()` and `abs(1, 2)`).
- A name used without parentheses is always a variable, even if it is also a function name: `abs` alone raises `ExpressionError` unless `variables` defines `abs`. A name followed by `(` is always a function call, so a variable called like a function (`x(1)`) is an unknown function.
- Variables may hold ints or floats. The `variables` dict is not modified.
