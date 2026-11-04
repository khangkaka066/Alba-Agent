Build a small in-memory SQL engine in this directory using only the Python standard library. `errors.py` already exists (`class SqlError(Exception)`); every problem with a statement must raise `SqlError`. Create exactly these modules with exactly these names and signatures; a grader tests each module on its own and then the whole.

## tokenizer.py
`tokenize(sql: str) -> list[tuple[str, object]]` returns `(kind, value)` pairs:
- `"kw"`: a keyword, value upper-cased. Keywords (case-insensitive): SELECT FROM WHERE ORDER BY ASC DESC LIMIT INSERT INTO VALUES UPDATE SET DELETE CREATE TABLE PRIMARY KEY AND OR NOT NULL IS BEGIN COMMIT ROLLBACK INT TEXT.
- `"id"`: an identifier `[A-Za-z_][A-Za-z0-9_]*` that is not a keyword, case preserved.
- `"num"`: an int, or a float when it contains `.`. A number may start with `-` (there is no subtraction).
- `"str"`: text between single quotes, quotes removed; `''` inside the quotes is one quote character.
- `"op"`: one of `=  !=  <  <=  >  >=`; `<>` is returned as `!=`.
- `"p"`: one of `(  )  ,  *  ;`.
Whitespace is ignored. An unterminated string or any other character raises `SqlError`.

## parser.py
`parse(tokens) -> dict` takes the tokenizer's output and returns one statement:
- `{"type": "create", "table": str, "columns": [(name, "INT"|"TEXT", is_primary_key), ...]}` for `CREATE TABLE t (a INT PRIMARY KEY, b TEXT)`.
- `{"type": "insert", "table": str, "columns": [str, ...] or None, "rows": [[literal, ...], ...]}` for `INSERT INTO t [(a, b)] VALUES (1, 'x'), (2, 'y')`.
- `{"type": "select", "table": str, "columns": [str, ...] or None, "where": expr or None, "order": (column, "ASC"|"DESC") or None, "limit": int or None}`; `*` gives `columns` None; `ORDER BY c` means ASC; syntax `SELECT cols FROM t [WHERE expr] [ORDER BY c [ASC|DESC]] [LIMIT n]`.
- `{"type": "update", "table": str, "set": [(column, literal), ...], "where": expr or None}` for `UPDATE t SET a = 1, b = 'x' [WHERE expr]`.
- `{"type": "delete", "table": str, "where": expr or None}` for `DELETE FROM t [WHERE expr]`.
- `{"type": "begin"}`, `{"type": "commit"}`, `{"type": "rollback"}`.
A literal is an int, float, str or None (for `NULL`). An expression is a nested tuple: `("cmp", op, left, right)` with op one of `= != < <= > >=`, `("and", a, b)`, `("or", a, b)`, `("not", a)`, `("isnull", operand, negated)` for `x IS NULL` (negated False) and `x IS NOT NULL` (negated True). An operand is `("col", name)` or `("lit", value)`. Precedence from tightest: NOT, AND, OR; parentheses group; AND and OR associate to the left, so `a OR b OR c` is `("or", ("or", a, b), c)`. One trailing `;` is allowed. Any missing or extra token raises `SqlError`.

## evaluator.py
`evaluate(expr, row: dict) -> bool | None` evaluates an expression against a row with SQL three-valued logic: a comparison with a `None` operand is `None`; `AND`/`OR`/`NOT` follow the usual three-valued rules (False AND None is False, True OR None is True, NOT None is None); `isnull` is always True or False. Comparing a str with a number raises `SqlError`, and so does a column the row does not have. `matches(expr, row) -> bool` is True only when `evaluate` returns True; an `expr` of `None` always matches.

## storage.py
`class Storage` with:
- `create_table(name, columns)` where `columns` is the parser's list of `(name, type, is_primary_key)`; `SqlError` if the table exists, there are no columns, a column name repeats, or more than one primary key.
- `table_columns(name) -> list[str]` in declaration order; `SqlError` for an unknown table.
- `insert_many(name, rows: list[dict]) -> int` where each dict has exactly the table's columns. INT accepts int (not bool) or None, TEXT accepts str or None, a primary key may be neither None nor a duplicate (also within the same call). The call is atomic: if any row is rejected, no row is added. Returns the number of rows added.
- `rows(name) -> list[dict]` copies, in insertion order.
- `update(name, predicate, changes: dict) -> int` applies `changes` to every row for which `predicate(row)` is True and returns how many rows matched; the same type and primary-key rules apply and the call is atomic.
- `delete(name, predicate) -> int` removes matching rows and returns how many.
- `begin()`, `commit()`, `rollback()`: one level of transaction; `rollback` restores every table to the state at `begin`, including tables created and rows changed since. `begin` inside a transaction, or `commit`/`rollback` outside one, raises `SqlError`.

## engine.py
`class Engine` with `execute(sql: str) -> Result`, where `Result` is a dataclass with `columns: list[str]`, `rows: list[tuple]` and `rowcount: int = 0`. `execute` tokenizes, parses and runs one statement against a `Storage` the engine owns.
- `CREATE`: rowcount 0, no rows.
- `INSERT`: when no column list is given the values are for all columns in order; the value count must match the column count; unlisted columns are None; rowcount is the number of rows inserted and the statement is atomic.
- `SELECT`: `columns` is the selected names, or all columns for `*`; `rows` are tuples in that order; unknown columns raise `SqlError`. `ORDER BY` is stable, NULLs sort first when ascending and last when descending; `LIMIT` applies after ordering. rowcount is the number of rows returned.
- `UPDATE` and `DELETE`: rowcount is the number of matching rows.
- `BEGIN`, `COMMIT`, `ROLLBACK`: delegate to the storage.
Table and column names are case-sensitive.
