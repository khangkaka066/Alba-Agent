import unittest

from engine import Engine, Result
from errors import SqlError


def engine():
    e = Engine()
    e.execute("CREATE TABLE users (id INT PRIMARY KEY, name TEXT, age INT)")
    e.execute("INSERT INTO users VALUES (1, 'ann', 30), (2, 'bob', NULL), (3, 'cy', 25), (4, 'di', 30)")
    return e


class EngineTests(unittest.TestCase):
    def test_result_shape_and_create(self):
        e = Engine()
        r = e.execute("CREATE TABLE t (a INT)")
        self.assertIsInstance(r, Result)
        self.assertEqual((r.columns, r.rows, r.rowcount), ([], [], 0))

    def test_insert_counts_and_column_lists(self):
        e = Engine()
        e.execute("CREATE TABLE t (a INT, b TEXT, c INT)")
        self.assertEqual(e.execute("INSERT INTO t (c, a) VALUES (3, 1), (6, 4)").rowcount, 2)
        self.assertEqual(e.execute("SELECT * FROM t").rows, [(1, None, 3), (4, None, 6)])

    def test_insert_errors_and_atomicity(self):
        e = engine()
        for bad in ("INSERT INTO users VALUES (9, 'x')", "INSERT INTO users (id, nope) VALUES (9, 1)",
                    "INSERT INTO users (id, id) VALUES (9, 1)", "INSERT INTO users VALUES (1, 'dup', 1)",
                    "INSERT INTO users VALUES (10, 'ok', 1), (1, 'dup', 1)", "INSERT INTO nope VALUES (1)",
                    "INSERT INTO users VALUES ('x', 'y', 1)"):
            with self.assertRaises(SqlError, msg=bad):
                e.execute(bad)
        self.assertEqual(e.execute("SELECT id FROM users").rowcount, 4)

    def test_select_columns_star_and_where(self):
        e = engine()
        r = e.execute("SELECT name, id FROM users WHERE age = 30")
        self.assertEqual((r.columns, r.rows, r.rowcount), (["name", "id"], [("ann", 1), ("di", 4)], 2))
        self.assertEqual(e.execute("SELECT * FROM users WHERE id = 3").columns, ["id", "name", "age"])

    def test_null_semantics_in_where(self):
        e = engine()
        self.assertEqual(e.execute("SELECT id FROM users WHERE age != 30").rows, [(3,)])
        self.assertEqual(e.execute("SELECT id FROM users WHERE age IS NULL").rows, [(2,)])
        self.assertEqual(e.execute("SELECT id FROM users WHERE age IS NOT NULL AND NOT age = 25").rows, [(1,), (4,)])
        self.assertEqual(e.execute("SELECT id FROM users WHERE NOT age = 30").rows, [(3,)])
        self.assertEqual(e.execute("SELECT id FROM users WHERE age = 30 OR age IS NULL").rows, [(1,), (2,), (4,)])

    def test_order_by_nulls_stability_and_limit(self):
        e = engine()
        self.assertEqual(e.execute("SELECT id FROM users ORDER BY age").rows, [(2,), (3,), (1,), (4,)])
        self.assertEqual(e.execute("SELECT id FROM users ORDER BY age DESC").rows, [(1,), (4,), (3,), (2,)])
        self.assertEqual(e.execute("SELECT name FROM users ORDER BY name DESC LIMIT 2").rows, [("di",), ("cy",)])
        r = e.execute("SELECT id FROM users ORDER BY age LIMIT 1")
        self.assertEqual((r.rows, r.rowcount), ([(2,)], 1))
        self.assertEqual(e.execute("SELECT id FROM users LIMIT 0").rows, [])
        self.assertEqual(e.execute("SELECT id FROM users WHERE age = 30 ORDER BY age DESC").rows, [(1,), (4,)])

    def test_select_errors(self):
        e = engine()
        for bad in ("SELECT nope FROM users", "SELECT id FROM users ORDER BY nope", "SELECT id FROM nope",
                    "SELECT id FROM users WHERE nope = 1", "SELECT id FROM users WHERE name = 5"):
            with self.assertRaises(SqlError, msg=bad):
                e.execute(bad)

    def test_update_and_delete_counts(self):
        e = engine()
        self.assertEqual(e.execute("UPDATE users SET age = 31 WHERE age = 30").rowcount, 2)
        self.assertEqual(e.execute("SELECT id FROM users WHERE age = 31").rows, [(1,), (4,)])
        self.assertEqual(e.execute("UPDATE users SET name = 'x' WHERE id = 99").rowcount, 0)
        self.assertEqual(e.execute("DELETE FROM users WHERE age IS NULL").rowcount, 1)
        self.assertEqual(e.execute("DELETE FROM users").rowcount, 3)
        self.assertEqual(e.execute("SELECT * FROM users").rows, [])

    def test_update_errors_leave_data_unchanged(self):
        e = engine()
        for bad in ("UPDATE users SET id = 1 WHERE id = 2", "UPDATE users SET nope = 1", "UPDATE users SET age = 'old'"):
            with self.assertRaises(SqlError, msg=bad):
                e.execute(bad)
        self.assertEqual(e.execute("SELECT id, age FROM users ORDER BY id").rows, [(1, 30), (2, None), (3, 25), (4, 30)])

    def test_transactions_through_sql(self):
        e = engine()
        e.execute("BEGIN")
        e.execute("DELETE FROM users WHERE id = 1")
        e.execute("CREATE TABLE tmp (a INT)")
        e.execute("ROLLBACK")
        self.assertEqual(e.execute("SELECT id FROM users").rowcount, 4)
        with self.assertRaises(SqlError):
            e.execute("SELECT * FROM tmp")
        e.execute("BEGIN")
        e.execute("UPDATE users SET age = 1")
        e.execute("COMMIT")
        self.assertEqual({row[0] for row in e.execute("SELECT age FROM users").rows}, {1})
        for bad in ("COMMIT", "ROLLBACK"):
            with self.assertRaises(SqlError):
                e.execute(bad)

    def test_strings_with_quotes_semicolons_and_keywords_round_trip(self):
        e = Engine()
        e.execute("CREATE TABLE notes (id INT PRIMARY KEY, body TEXT)")
        e.execute("INSERT INTO notes VALUES (1, 'it''s; SELECT * FROM x'), (2, '')")
        self.assertEqual(e.execute("SELECT body FROM notes WHERE id = 1").rows, [("it's; SELECT * FROM x",)])
        self.assertEqual(e.execute("SELECT id FROM notes WHERE body = ''").rows, [(2,)])

    def test_statements_are_case_insensitive_but_names_are_not(self):
        e = engine()
        self.assertEqual(e.execute("select id from users where id = 1;").rows, [(1,)])
        for bad in ("SELECT ID FROM users", "SELECT id FROM USERS"):
            with self.assertRaises(SqlError):
                e.execute(bad)

    def test_two_engines_do_not_share_data(self):
        a, b = engine(), Engine()
        with self.assertRaises(SqlError):
            b.execute("SELECT * FROM users")
        self.assertEqual(a.execute("SELECT id FROM users").rowcount, 4)


if __name__ == "__main__":
    unittest.main()
