import copy

from errors import SqlError


class Storage:
    def __init__(self):
        self._tables = {}
        self._snapshot = None

    def _table(self, name):
        if name not in self._tables:
            raise SqlError(f"unknown table {name}")
        return self._tables[name]

    def create_table(self, name, columns):
        if name in self._tables:
            raise SqlError(f"table {name} exists")
        names = [column[0] for column in columns]
        if not columns or len(set(names)) != len(names) or sum(1 for column in columns if column[2]) > 1:
            raise SqlError("invalid table definition")
        self._tables[name] = {"columns": [tuple(column) for column in columns], "rows": []}

    def table_columns(self, name):
        return [column[0] for column in self._table(name)["columns"]]

    @staticmethod
    def _check(table, row):
        for name, type_name, _ in table["columns"]:
            value = row[name]
            if value is None:
                continue
            ok = isinstance(value, int) and not isinstance(value, bool) if type_name == "INT" else isinstance(value, str)
            if not ok:
                raise SqlError(f"{name} expects {type_name}")

    @staticmethod
    def _check_keys(table, rows):
        keys = [name for name, _, primary in table["columns"] if primary]
        if not keys:
            return
        seen = set()
        for row in rows:
            value = row[keys[0]]
            if value is None or value in seen:
                raise SqlError("primary key must be present and unique")
            seen.add(value)

    def insert_many(self, name, rows):
        table = self._table(name)
        columns = {column[0] for column in table["columns"]}
        new_rows = []
        for row in rows:
            if set(row) != columns:
                raise SqlError("a row must have exactly the table's columns")
            self._check(table, row)
            new_rows.append(dict(row))
        self._check_keys(table, table["rows"] + new_rows)
        table["rows"].extend(new_rows)
        return len(new_rows)

    def rows(self, name):
        return [dict(row) for row in self._table(name)["rows"]]

    def update(self, name, predicate, changes):
        table = self._table(name)
        columns = {column[0] for column in table["columns"]}
        if not set(changes) <= columns:
            raise SqlError("unknown column in SET")
        updated, count = [], 0
        for row in table["rows"]:
            if predicate(dict(row)):
                count += 1
                row = {**row, **changes}
                self._check(table, row)
            updated.append(row)
        self._check_keys(table, updated)
        table["rows"] = updated
        return count

    def delete(self, name, predicate):
        table = self._table(name)
        kept = [row for row in table["rows"] if not predicate(dict(row))]
        removed = len(table["rows"]) - len(kept)
        table["rows"] = kept
        return removed

    def begin(self):
        if self._snapshot is not None:
            raise SqlError("already in a transaction")
        self._snapshot = copy.deepcopy(self._tables)

    def commit(self):
        if self._snapshot is None:
            raise SqlError("no transaction")
        self._snapshot = None

    def rollback(self):
        if self._snapshot is None:
            raise SqlError("no transaction")
        self._tables, self._snapshot = self._snapshot, None
