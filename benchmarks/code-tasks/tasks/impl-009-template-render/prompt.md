Implement `render(template: str, context: dict) -> str` in `templating.py`: a tiny `{{ ... }}` template engine.

Tags
- A tag is `{{`, an expression, and the first following `}}`. Text outside tags is copied unchanged.
- The expression is split on `|`: the first part is a variable path, every following part is a filter. Whitespace around every part is ignored (`{{ user.name|upper }}` and `{{  user.name  |  upper  }}` are the same).
- A `{{` with no later `}}` raises `ValueError`.
- The two-character sequence `\{{` (backslash then two braces) is an escape: it outputs the literal text `{{` (the backslash is dropped) and does not start a tag. Anything after it is ordinary text until the next real `{{`.

Variable paths
- A path is dot-separated segments; the first segment is an identifier (`[A-Za-z_][A-Za-z0-9_]*`), later segments are made of `[A-Za-z0-9_]`. An empty expression or an invalid path raises `ValueError`.
- Lookup starts at `context`. For each segment: if the current value is a `dict`, use the key equal to the segment; if it is a `list` or `tuple` and the segment is all digits, use that zero-based index. Anything else, a missing key, or an out-of-range index means the path is "missing".

Rendering a value
- The final value is converted with `str()`, except `None`, which renders as the empty string.
- A missing path raises `KeyError` (unless a `default` filter handles it, see below).

Filters (applied left to right)
- `upper` and `lower`: convert the `str()` of the current value to upper/lower case (`None` counts as `""`). A missing value reaching `upper`/`lower` raises `KeyError`.
- `default:"text"`: the filter name, a colon, then a double-quoted literal. The literal contains no `"` and no `|` and may be empty. If the current value is missing or `None`, it is replaced with `text`; otherwise it is left untouched. After a `default` filter, the value is never missing.
- Any other filter name, or a malformed `default` filter (e.g. no quotes), raises `ValueError`.

Examples: `render("Hi {{ user.name | default:"guest" | upper }}!", {})` -> `"Hi GUEST!"`; `render("{{ items.1 }}", {"items": ["a", "b"]})` -> `"b"`.
