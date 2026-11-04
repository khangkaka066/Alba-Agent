Implement `slugify(text)` in `slug.py`.

It turns a title into a URL slug:
- lowercase ASCII letters and digits only, words joined by a single `-`
- accented Latin letters are reduced to their base letter (`é` -> `e`); `đ` -> `d`
- any run of other characters (spaces, punctuation, symbols) is one separator
- no leading or trailing `-`
- an input with no letters or digits returns `""`
