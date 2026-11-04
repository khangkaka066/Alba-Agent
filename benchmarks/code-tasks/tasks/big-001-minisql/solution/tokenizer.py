import re

from errors import SqlError

KEYWORDS = frozenset(
    "SELECT FROM WHERE ORDER BY ASC DESC LIMIT INSERT INTO VALUES UPDATE SET DELETE CREATE TABLE PRIMARY KEY "
    "AND OR NOT NULL IS BEGIN COMMIT ROLLBACK INT TEXT".split()
)
_TOKEN = re.compile(
    r"\s+|(?P<num>-?\d+\.\d+|-?\d+)|(?P<id>[A-Za-z_][A-Za-z0-9_]*)|(?P<str>'(?:[^']|'')*')"
    r"|(?P<op><=|>=|<>|!=|=|<|>)|(?P<p>[(),*;])"
)


def tokenize(sql):
    tokens = []
    position = 0
    while position < len(sql):
        match = _TOKEN.match(sql, position)
        if not match:
            raise SqlError(f"unexpected character {sql[position]!r} at {position}")
        position = match.end()
        kind, text = match.lastgroup, match.group()
        if kind is None:
            continue
        if kind == "num":
            tokens.append(("num", float(text) if "." in text else int(text)))
        elif kind == "id":
            upper = text.upper()
            tokens.append(("kw", upper) if upper in KEYWORDS else ("id", text))
        elif kind == "str":
            tokens.append(("str", text[1:-1].replace("''", "'")))
        elif kind == "op":
            tokens.append(("op", "!=" if text == "<>" else text))
        else:
            tokens.append(("p", text))
    return tokens
