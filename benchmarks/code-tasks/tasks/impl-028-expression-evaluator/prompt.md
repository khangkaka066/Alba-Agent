Pricing rules in our admin panel are typed as formulas such as `base * (1 + tax) - discount`, and we must evaluate them safely (no `eval`, no `ast`-based shortcuts: write a real tokenizer and parser). Implement `evaluate(expression, variables=None)` and the exceptions in `calc.py`.

**Tokens.** Whitespace between tokens is ignored. Numbers are `digits` or `digits.digits` (`3`, `2.50`; not `.5`, not `5.`); a number without a dot is an `int`, with a dot a `float`. Identifiers start with a letter or `_` and continue with letters, digits or `_`. Operators and punctuation: `+ - * / % ^ ( ) ,`. Any other character is a syntax error. There is no implicit multiplication (`2x`, `2(3)` and `(1)(2)` are syntax errors).

**Grammar and precedence** (highest first):
1. Atoms: a number, a variable name, a function call `name(arg, arg, ...)`, or a parenthesised expression.
2. `^` power, **right-associative** (`2^3^2 == 2^(3^2) == 512`). Its right operand may start with a unary sign (`2^-2 == 0.25`).
3. Unary `+` and `-` (they may be repeated: `--3 == 3`). Unary minus binds looser than `^`, so `-2^2 == -4`, while `(-2)^2 == 4`.
4. `*`, `/`, `%`, left-associative.
5. `+`, `-`, left-associative.

**Semantics.**
- Arithmetic follows Python: `+ - * %` on two ints give an int, `%` is Python's floored modulo, `/` is true division and always gives a float (`6/3 == 2.0`), and `^` is Python's `**` (so `2^-1 == 0.5`, `2^10 == 1024`).
- Variables come from the `variables` dict (name -> int or float); `None` means no variables.
- Functions (always available, case-sensitive): `abs(x)` takes exactly one argument; `min(...)` and `max(...)` take one or more. A function name used with `(` is always a function call, even if `variables` has the same name; a name without `(` is always a variable lookup.
- Operands are evaluated left to right, depth first.

**Errors.** The whole expression is parsed before anything is evaluated, so syntax errors take precedence over evaluation errors.
- `ExprError(ValueError)` is the base class. `ExprSyntaxError(ExprError)` is raised for an empty/blank expression, an illegal character, a missing or unexpected token, unbalanced parentheses, trailing tokens, and a wrong number of arguments to a function (including `max()`).
- `UndefinedNameError(ExprError)` is raised at evaluation time for an unknown variable or an unknown function name.
- Division or modulo by zero, and `0` raised to a negative power, raise the builtin `ZeroDivisionError`.
- Raising a negative number to a non-integer power (for example `(-8)^0.5`) raises a plain `ExprError`.
