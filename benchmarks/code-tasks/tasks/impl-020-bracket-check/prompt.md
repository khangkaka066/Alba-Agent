Our config linter needs to report the first bracket problem in a snippet of source text. Implement `find_bracket_error(text)` in `brackets.py`.

It scans `text` left to right (indexes are 0-based positions in `text`) and returns `None` if the text is fine, otherwise a tuple `(kind, index)` describing the **first** problem found, where `kind` is one of the strings below.

Bracket pairs are `()`, `[]` and `{}`.

Text that must be ignored while scanning (brackets inside it are neither opening nor closing):
- String literals delimited by `"` or `'`. Inside a string a backslash escapes the next character (so `\"` does not end a `"` string, and `\\` is a literal backslash). A string ends at the next unescaped quote of the same kind. A string cannot span lines: if a newline, or the end of the text, is reached before the string is closed, the result is `("unterminated_string", index_of_the_opening_quote)`.
- Comments: a `#` outside a string starts a comment that runs to the end of the line (up to, not including, the next `\n`).

Problems, checked as the scan proceeds:
- `("unexpected_closer", i)`: a closing bracket at index `i` when no bracket is currently open.
- `("mismatched", i)`: a closing bracket at index `i` that does not match the most recently opened bracket.
- `("unclosed", i)`: reported only once the whole text has been scanned without any of the problems above, if brackets remain open; `i` is the index of the most recently opened bracket that is still open (the innermost one).

Also implement `is_balanced(text)`, which returns `True` exactly when `find_bracket_error(text)` is `None`.
