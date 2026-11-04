import unittest

from errors import SqlError
from parser import parse
from tokenizer import tokenize


def p(sql):
    return parse(tokenize(sql))


class ParserTests(unittest.TestCase):
    def test_create(self):
        self.assertEqual(p("CREATE TABLE t (id INT PRIMARY KEY, name TEXT, n INT)"),
                         {"type": "create", "table": "t", "columns": [("id", "INT", True), ("name", "TEXT", False), ("n", "INT", False)]})

    def test_insert_with_and_without_columns_and_many_rows(self):
        self.assertEqual(p("INSERT INTO t VALUES (1, 'a', NULL)"),
                         {"type": "insert", "table": "t", "columns": None, "rows": [[1, "a", None]]})
        self.assertEqual(p("insert into t (b, a) values (1.5, 'x'), (2, 'y');"),
                         {"type": "insert", "table": "t", "columns": ["b", "a"], "rows": [[1.5, "x"], [2, "y"]]})

    def test_select_star_and_columns_with_clauses(self):
        self.assertEqual(p("SELECT * FROM t"),
                         {"type": "select", "table": "t", "columns": None, "where": None, "order": None, "limit": None})
        self.assertEqual(p("SELECT a, b FROM t WHERE a = 1 ORDER BY b DESC LIMIT 5"),
                         {"type": "select", "table": "t", "columns": ["a", "b"], "where": ("cmp", "=", ("col", "a"), ("lit", 1)),
                          "order": ("b", "DESC"), "limit": 5})
        self.assertEqual(p("SELECT a FROM t ORDER BY a")["order"], ("a", "ASC"))
        self.assertEqual(p("SELECT a FROM t ORDER BY a ASC")["order"], ("a", "ASC"))

    def test_update_and_delete(self):
        self.assertEqual(p("UPDATE t SET a = 1, b = 'x' WHERE id = 2"),
                         {"type": "update", "table": "t", "set": [("a", 1), ("b", "x")], "where": ("cmp", "=", ("col", "id"), ("lit", 2))})
        self.assertEqual(p("DELETE FROM t"), {"type": "delete", "table": "t", "where": None})
        self.assertEqual(p("DELETE FROM t WHERE a IS NULL")["where"], ("isnull", ("col", "a"), False))

    def test_transaction_statements(self):
        for word in ("begin", "COMMIT", "Rollback"):
            self.assertEqual(p(word), {"type": word.lower()})

    def test_precedence_not_and_or(self):
        where = p("SELECT a FROM t WHERE a = 1 OR b = 2 AND NOT c = 3")["where"]
        a, b, c = (("cmp", "=", ("col", n), ("lit", v)) for n, v in (("a", 1), ("b", 2), ("c", 3)))
        self.assertEqual(where, ("or", a, ("and", b, ("not", c))))

    def test_left_association_and_parentheses(self):
        a, b, c = (("cmp", "=", ("col", n), ("lit", 1)) for n in "abc")
        self.assertEqual(p("SELECT x FROM t WHERE a = 1 OR b = 1 OR c = 1")["where"], ("or", ("or", a, b), c))
        self.assertEqual(p("SELECT x FROM t WHERE (a = 1 OR b = 1) AND c = 1")["where"], ("and", ("or", a, b), c))

    def test_is_not_null_and_operators_and_literal_on_the_left(self):
        self.assertEqual(p("SELECT a FROM t WHERE a IS NOT NULL")["where"], ("isnull", ("col", "a"), True))
        self.assertEqual(p("SELECT a FROM t WHERE 3 <> a")["where"], ("cmp", "!=", ("lit", 3), ("col", "a")))
        self.assertEqual(p("SELECT a FROM t WHERE a >= 'm'")["where"], ("cmp", ">=", ("col", "a"), ("lit", "m")))

    def test_trailing_semicolon_allowed_once(self):
        self.assertEqual(p("DELETE FROM t;"), p("DELETE FROM t"))
        with self.assertRaises(SqlError):
            p("DELETE FROM t;;")

    def test_malformed_statements_raise(self):
        for bad in ("", "SELECT", "SELECT a", "SELECT a FROM", "SELECT FROM t", "CREATE TABLE t ()", "CREATE TABLE t (a FLOAT)",
                    "INSERT INTO t VALUES", "INSERT INTO t VALUES (1", "UPDATE t SET", "UPDATE t SET a 1",
                    "SELECT a FROM t WHERE", "SELECT a FROM t WHERE a", "SELECT a FROM t LIMIT x", "SELECT a FROM t LIMIT 1.5",
                    "SELECT a FROM t extra", "DROP TABLE t", "BEGIN now", "SELECT a FROM t WHERE (a = 1"):
            with self.assertRaises(SqlError, msg=bad):
                p(bad)


if __name__ == "__main__":
    unittest.main()
