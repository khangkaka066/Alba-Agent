We import customer exports from spreadsheets and cannot rely on the `csv` module being used by whoever produced them, so we need our own small reader and writer. Implement `parse_csv` and `to_csv` in `csvlite.py` (do not import the `csv` module).

**`parse_csv(text, delimiter=",") -> list[list[str]]`**
- `delimiter` must be a single character that is not `"`, `\n` or `\r`; otherwise `ValueError` (raised even for empty `text`).
- Records are separated by `\n` or `\r\n`. A terminator after the last record does not create another record. Empty `text` gives `[]`.
- Completely empty lines (a terminator with nothing before it, including a line that is only `\r\n`) are skipped and produce no record.
- Fields are separated by the delimiter. Nothing is trimmed: spaces are part of the field. `a,b,` has three fields (the last is `""`) and a line consisting only of the delimiter has two empty fields.
- A field that **starts** with `"` is a quoted field. It extends to the closing quote; inside it `""` stands for one literal `"`, and the delimiter, `\n` and `\r` are ordinary characters kept exactly as they appear. After the closing quote the next character must be the delimiter, a record terminator or the end of the text; anything else raises `ValueError`. A quoted field that is never closed raises `ValueError`. A quoted empty field (`""`) is a real field with the value `""`, so a line `""` is the record `[""]`.
- A `"` anywhere other than the start of a field is an ordinary character. A lone `\r` not followed by `\n`, outside quotes, is also an ordinary character.

**`to_csv(rows, delimiter=",") -> str`**
- `rows` is a list of rows, each row a non-empty list of `str`. A row that is empty raises `ValueError`; a field that is not a `str` raises `TypeError`. The delimiter is validated as above.
- Every row is written followed by `\n` (so no rows gives `""`).
- A field is wrapped in double quotes (with each inner `"` doubled) when it contains the delimiter, `"`, `\n` or `\r`; or when it is the empty string and the row has only that one field (so that the line is not blank). All other fields are written as they are.
- For valid input, `parse_csv(to_csv(rows, d), d) == rows`.
