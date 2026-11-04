Implement `parse_ini` and `get_bool` in `inifile.py`.

`parse_ini(text: str) -> dict[str, dict[str, str]]` parses INI-style text into `{section: {key: value}}`.

Line rules (text is split into lines on `\n`; a trailing `\r` is stripped; every line is also stripped of leading and trailing whitespace; line numbers in errors are 1-based):
- Blank lines are ignored. A line whose first character (after stripping) is `;` or `#` is a comment and is ignored. Comments only exist as whole lines: a `;` or `#` later in a line is part of the value.
- `[name]` starts a section. The name is the text between the brackets, stripped of whitespace, and must be non-empty. A line that starts with `[` but does not end with `]`, or has an empty name, is an error. Section names are case-sensitive. A section header that appears again continues the same section (its keys merge into the existing dict).
- Any other line is `key = value` or `key: value`: split at whichever of `=` or `:` comes FIRST in the line. Key and value are stripped. The key must be non-empty. The value may be empty (`""`). Keys are case-sensitive and a repeated key in a section is overwritten by the later one.
- If the stripped value has length >= 2 and starts and ends with `"`, those two quote characters are removed (the content inside is kept as is, including surrounding spaces).
- Keys that appear before any section header go into the section named `""` (empty string). That section only exists in the result if at least one such key is present. A section that is declared but has no keys exists as an empty dict. Sections appear in the result in order of first appearance.
- A line that is not blank, not a comment, not a header and contains neither `=` nor `:`, or that has an empty key, raises `ValueError`. Every `ValueError` message from this function must contain the text `line N` where `N` is the 1-based number of the offending line (e.g. `"line 3"`).

`get_bool(config: dict[str, dict[str, str]], section: str, key: str, default: bool | None = None) -> bool | None`
- Looks up `config[section][key]`. If the section or the key is missing, return `default`.
- Otherwise compare the value case-insensitively (after stripping): `1`, `true`, `yes`, `on` -> `True`; `0`, `false`, `no`, `off` -> `False`; anything else raises `ValueError`.
