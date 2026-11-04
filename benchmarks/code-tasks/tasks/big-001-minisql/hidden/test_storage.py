import unittest

from errors import SqlError
from storage import Storage

COLS = [("id", "INT", True), ("name", "TEXT", False), ("n", "INT", False)]


def make():
    s = Storage()
    s.create_table("t", COLS)
    return s


class StorageTests(unittest.TestCase):
    def test_create_and_columns(self):
        s = make()
        self.assertEqual(s.table_columns("t"), ["id", "name", "n"])
        with self.assertRaises(SqlError):
            s.create_table("t", COLS)
        with self.assertRaises(SqlError):
            s.table_columns("nope")
        for bad in ([], [("a", "INT", False), ("a", "TEXT", False)], [("a", "INT", True), ("b", "INT", True)]):
            with self.assertRaises(SqlError):
                s.create_table("x", bad)

    def test_insert_and_rows_are_copies_in_order(self):
        s = make()
        self.assertEqual(s.insert_many("t", [{"id": 2, "name": "b", "n": None}, {"id": 1, "name": None, "n": 5}]), 2)
        rows = s.rows("t")
        self.assertEqual([r["id"] for r in rows], [2, 1])
        rows[0]["name"] = "changed"
        self.assertEqual(s.rows("t")[0]["name"], "b")

    def test_type_checks(self):
        s = make()
        for bad in ({"id": "x", "name": "a", "n": 1}, {"id": 1, "name": 5, "n": 1}, {"id": 1, "name": "a", "n": 1.5},
                    {"id": True, "name": "a", "n": 1}, {"id": 1, "name": "a", "n": False}):
            with self.assertRaises(SqlError, msg=str(bad)):
                s.insert_many("t", [bad])
        self.assertEqual(s.rows("t"), [])

    def test_rows_must_have_exactly_the_columns(self):
        s = make()
        for bad in ({"id": 1}, {"id": 1, "name": "a", "n": 1, "extra": 1}):
            with self.assertRaises(SqlError):
                s.insert_many("t", [bad])

    def test_primary_key_rules_and_atomic_insert(self):
        s = make()
        s.insert_many("t", [{"id": 1, "name": "a", "n": 1}])
        with self.assertRaises(SqlError):
            s.insert_many("t", [{"id": 2, "name": "b", "n": 1}, {"id": 1, "name": "dup", "n": 1}])
        self.assertEqual(len(s.rows("t")), 1)
        with self.assertRaises(SqlError):
            s.insert_many("t", [{"id": 5, "name": "x", "n": 1}, {"id": 5, "name": "y", "n": 1}])
        with self.assertRaises(SqlError):
            s.insert_many("t", [{"id": None, "name": "x", "n": 1}])
        self.assertEqual(len(s.rows("t")), 1)

    def test_update_counts_matches_and_is_atomic(self):
        s = make()
        s.insert_many("t", [{"id": i, "name": "a", "n": i} for i in (1, 2, 3)])
        self.assertEqual(s.update("t", lambda r: r["n"] >= 2, {"name": "z"}), 2)
        self.assertEqual([r["name"] for r in s.rows("t")], ["a", "z", "z"])
        self.assertEqual(s.update("t", lambda r: False, {"name": "q"}), 0)
        with self.assertRaises(SqlError):
            s.update("t", lambda r: True, {"id": 1})
        self.assertEqual([r["id"] for r in s.rows("t")], [1, 2, 3])
        with self.assertRaises(SqlError):
            s.update("t", lambda r: r["id"] == 3, {"n": "text"})
        with self.assertRaises(SqlError):
            s.update("t", lambda r: True, {"nope": 1})
        self.assertEqual(s.rows("t")[2]["n"], 3)

    def test_update_may_keep_or_change_a_key_to_a_free_value(self):
        s = make()
        s.insert_many("t", [{"id": 1, "name": "a", "n": 1}, {"id": 2, "name": "b", "n": 2}])
        self.assertEqual(s.update("t", lambda r: r["id"] == 2, {"id": 3}), 1)
        self.assertEqual(sorted(r["id"] for r in s.rows("t")), [1, 3])
        self.assertEqual(s.update("t", lambda r: r["id"] == 1, {"id": 1}), 1)

    def test_delete(self):
        s = make()
        s.insert_many("t", [{"id": i, "name": None, "n": None} for i in (1, 2, 3)])
        self.assertEqual(s.delete("t", lambda r: r["id"] != 2), 2)
        self.assertEqual([r["id"] for r in s.rows("t")], [2])
        self.assertEqual(s.delete("t", lambda r: False), 0)

    def test_transaction_rollback_restores_everything(self):
        s = make()
        s.insert_many("t", [{"id": 1, "name": "a", "n": 1}])
        s.begin()
        s.insert_many("t", [{"id": 2, "name": "b", "n": 2}])
        s.update("t", lambda r: True, {"name": "changed"})
        s.delete("t", lambda r: r["id"] == 1)
        s.create_table("u", [("x", "INT", False)])
        s.rollback()
        self.assertEqual(s.rows("t"), [{"id": 1, "name": "a", "n": 1}])
        with self.assertRaises(SqlError):
            s.table_columns("u")

    def test_commit_keeps_changes_and_transaction_state_errors(self):
        s = make()
        s.begin()
        s.insert_many("t", [{"id": 1, "name": "a", "n": 1}])
        with self.assertRaises(SqlError):
            s.begin()
        s.commit()
        self.assertEqual(len(s.rows("t")), 1)
        for call in (s.commit, s.rollback):
            with self.assertRaises(SqlError):
                call()
        s.begin()
        s.rollback()
        s.begin()
        s.commit()

    def test_rolled_back_transaction_can_be_followed_by_another(self):
        s = make()
        s.begin()
        s.insert_many("t", [{"id": 1, "name": "a", "n": 1}])
        s.rollback()
        s.begin()
        s.insert_many("t", [{"id": 9, "name": "z", "n": 9}])
        s.commit()
        self.assertEqual([r["id"] for r in s.rows("t")], [9])


if __name__ == "__main__":
    unittest.main()
