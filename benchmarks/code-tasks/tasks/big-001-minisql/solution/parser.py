from errors import SqlError


class _Parser:
    def __init__(self, tokens):
        self.tokens = list(tokens)
        self.index = 0

    def peek(self):
        return self.tokens[self.index] if self.index < len(self.tokens) else (None, None)

    def take(self):
        token = self.peek()
        if token[0] is None:
            raise SqlError("unexpected end of statement")
        self.index += 1
        return token

    def accept(self, kind, value):
        if self.peek() == (kind, value):
            self.index += 1
            return True
        return False

    def expect(self, kind, value):
        if not self.accept(kind, value):
            raise SqlError(f"expected {value}")

    def identifier(self):
        kind, value = self.take()
        if kind != "id":
            raise SqlError("expected a name")
        return value

    def literal(self):
        kind, value = self.take()
        if kind in ("num", "str"):
            return value
        if (kind, value) == ("kw", "NULL"):
            return None
        raise SqlError("expected a value")

    def operand(self):
        kind, value = self.peek()
        if kind == "id":
            self.index += 1
            return ("col", value)
        return ("lit", self.literal())

    def expression(self):
        left = self.and_expression()
        while self.accept("kw", "OR"):
            left = ("or", left, self.and_expression())
        return left

    def and_expression(self):
        left = self.not_expression()
        while self.accept("kw", "AND"):
            left = ("and", left, self.not_expression())
        return left

    def not_expression(self):
        if self.accept("kw", "NOT"):
            return ("not", self.not_expression())
        if self.accept("p", "("):
            inner = self.expression()
            self.expect("p", ")")
            return inner
        left = self.operand()
        if self.accept("kw", "IS"):
            negated = self.accept("kw", "NOT")
            self.expect("kw", "NULL")
            return ("isnull", left, negated)
        kind, value = self.take()
        if kind != "op":
            raise SqlError("expected a comparison")
        return ("cmp", value, left, self.operand())

    def where(self):
        return self.expression() if self.accept("kw", "WHERE") else None

    def name_list(self):
        names = [self.identifier()]
        while self.accept("p", ","):
            names.append(self.identifier())
        return names

    def value_row(self):
        self.expect("p", "(")
        values = [self.literal()]
        while self.accept("p", ","):
            values.append(self.literal())
        self.expect("p", ")")
        return values

    def statement(self):
        kind, value = self.take()
        if kind != "kw":
            raise SqlError("expected a statement")
        if value in ("BEGIN", "COMMIT", "ROLLBACK"):
            return {"type": value.lower()}
        if value == "CREATE":
            self.expect("kw", "TABLE")
            table = self.identifier()
            self.expect("p", "(")
            columns = []
            while True:
                name = self.identifier()
                kind, type_name = self.take()
                if (kind, type_name) not in (("kw", "INT"), ("kw", "TEXT")):
                    raise SqlError("expected INT or TEXT")
                primary = False
                if self.accept("kw", "PRIMARY"):
                    self.expect("kw", "KEY")
                    primary = True
                columns.append((name, type_name, primary))
                if not self.accept("p", ","):
                    break
            self.expect("p", ")")
            return {"type": "create", "table": table, "columns": columns}
        if value == "INSERT":
            self.expect("kw", "INTO")
            table = self.identifier()
            columns = None
            if self.accept("p", "("):
                columns = self.name_list()
                self.expect("p", ")")
            self.expect("kw", "VALUES")
            rows = [self.value_row()]
            while self.accept("p", ","):
                rows.append(self.value_row())
            return {"type": "insert", "table": table, "columns": columns, "rows": rows}
        if value == "SELECT":
            columns = None
            if not self.accept("p", "*"):
                columns = self.name_list()
            self.expect("kw", "FROM")
            table = self.identifier()
            where = self.where()
            order = None
            if self.accept("kw", "ORDER"):
                self.expect("kw", "BY")
                column = self.identifier()
                if self.accept("kw", "DESC"):
                    direction = "DESC"
                else:
                    self.accept("kw", "ASC")
                    direction = "ASC"
                order = (column, direction)
            limit = None
            if self.accept("kw", "LIMIT"):
                kind, amount = self.take()
                if kind != "num" or not isinstance(amount, int) or amount < 0:
                    raise SqlError("LIMIT needs a non-negative integer")
                limit = amount
            return {"type": "select", "table": table, "columns": columns, "where": where, "order": order, "limit": limit}
        if value == "UPDATE":
            table = self.identifier()
            self.expect("kw", "SET")
            changes = []
            while True:
                column = self.identifier()
                self.expect("op", "=")
                changes.append((column, self.literal()))
                if not self.accept("p", ","):
                    break
            return {"type": "update", "table": table, "set": changes, "where": self.where()}
        if value == "DELETE":
            self.expect("kw", "FROM")
            table = self.identifier()
            return {"type": "delete", "table": table, "where": self.where()}
        raise SqlError(f"unsupported statement {value}")


def parse(tokens):
    parser = _Parser(tokens)
    result = parser.statement()
    parser.accept("p", ";")
    if parser.index != len(parser.tokens):
        raise SqlError("unexpected tokens after the statement")
    return result
