Webhook payload mappings are configured with short path strings like `order.items[0].sku`. Implement a tiny path reader in `jpath.py`.

**Path syntax.** A path is a sequence of steps:
- A *key step* is written as a bare name: one or more characters, none of which is `.`, `[`, `]` or `"` (spaces and digits are allowed, so `a.0` means the key `"0"`, never a list index). The first step may be a bare name; every later bare name must be preceded by a `.`.
- A *bracket step* is `[` ... `]` and is either an **index** (an optional leading `-` followed by one or more digits, e.g. `[0]`, `[-1]`) which becomes an `int`, or a **quoted key** written between double quotes, e.g. `["a.b"]`, which becomes a `str`. Inside the quotes `\"` stands for a double quote and `\\` for a backslash; any other backslash sequence, or a missing closing quote, is a syntax error. The empty quoted key `[""]` is allowed. A bracket step may be the first step (`[0].name`) or follow any other step directly (`a[0][1]`, `a["x"].b`) with no dot.
- The empty string is a valid path with zero steps.
- Anything else is a syntax error: a leading, trailing or doubled `.`, a `.` directly before `[`, text directly after `]` that is not `.` or `[`, an unclosed `[`, `[]`, `[abc]`, a stray `]` or `"`.

Syntax errors raise `PathSyntaxError`, a subclass of `ValueError`, and are raised even when the data would not contain the path.

**Functions**
- `parse_path(path) -> list[str | int]`: the steps in order, e.g. `parse_path('a.b[0]["x y"]') == ["a", "b", 0, "x y"]`.
- `get_path(data, path, default=None)`: follows the steps through `data`. A `str` step looks the key up in a `dict`; an `int` step indexes a `list` (negative indexes count from the end, as in Python). If at any step the container has the wrong type, the key is absent or the index is out of range, `default` is returned. The empty path returns `data` itself. The path is parsed first, so a syntax error is raised before any lookup. A stored value of `None` is returned as `None` (not `default`).
- `has_path(data, path) -> bool`: `True` if the whole path can be followed (even when the final value is `None`), `False` otherwise. Syntax errors raise `PathSyntaxError` here too.

Only `dict` and `list` are traversed (not tuples, strings or other objects); a `dict` is never indexed with an `int` step and a `list` never with a `str` step.
