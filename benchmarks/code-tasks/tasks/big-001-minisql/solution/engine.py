from dataclasses import dataclass, field

from errors import SqlError
from evaluator import matches
from parser import parse
from storage import Storage
from tokenizer import tokenize


@dataclass
class Result:
    columns: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    rowcount: int = 0


class Engine:
    def __init__(self):
        self.storage = Storage()

    def execute(self, sql):
        statement = parse(tokenize(sql))
        return getattr(self, "_" + statement["type"])(statement)

    def _create(self, statement):
        self.storage.create_table(statement["table"], statement["columns"])
        return Result()

    def _insert(self, statement):
        table = statement["table"]
        names = self.storage.table_columns(table)
        columns = statement["columns"] or names
        if len(set(columns)) != len(columns) or not set(columns) <= set(names):
            raise SqlError("bad column list")
        rows = []
        for values in statement["rows"]:
            if len(values) != len(columns):
                raise SqlError("value count does not match column count")
            row = {name: None for name in names}
            row.update(zip(columns, values))
            rows.append(row)
        return Result(rowcount=self.storage.insert_many(table, rows))

    def _select(self, statement):
        table = statement["table"]
        names = self.storage.table_columns(table)
        columns = statement["columns"] or names
        order = statement["order"]
        if not set(columns) <= set(names) or (order and order[0] not in names):
            raise SqlError("unknown column")
        rows = [row for row in self.storage.rows(table) if matches(statement["where"], row)]
        if order:
            column, direction = order
            present = sorted((row for row in rows if row[column] is not None), key=lambda row: row[column], reverse=direction == "DESC")
            missing = [row for row in rows if row[column] is None]
            rows = missing + present if direction == "ASC" else present + missing
        if statement["limit"] is not None:
            rows = rows[: statement["limit"]]
        return Result(list(columns), [tuple(row[name] for name in columns) for row in rows], len(rows))

    def _update(self, statement):
        where = statement["where"]
        return Result(rowcount=self.storage.update(statement["table"], lambda row: matches(where, row), dict(statement["set"])))

    def _delete(self, statement):
        where = statement["where"]
        return Result(rowcount=self.storage.delete(statement["table"], lambda row: matches(where, row)))

    def _begin(self, statement):
        self.storage.begin()
        return Result()

    def _commit(self, statement):
        self.storage.commit()
        return Result()

    def _rollback(self, statement):
        self.storage.rollback()
        return Result()
