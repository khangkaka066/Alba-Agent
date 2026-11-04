import unittest

from acl.audit import authorize
from acl.policy import can
from acl.roles import Role, effective_perms


class AclTests(unittest.TestCase):
    def test_deny_wins_even_when_listed_last(self):
        self.assertFalse(can(["doc:*", "!doc:delete"], "doc:delete"))
        self.assertTrue(can(["doc:*", "!doc:delete"], "doc:read"))

    def test_cycles_are_reported(self):
        roles = {"a": Role("a", parents=["b"]), "b": Role("b", parents=["a"])}
        with self.assertRaises(ValueError):
            effective_perms(roles, "a")

    def test_the_log_entry_is_a_sorted_snapshot(self):
        roles = {"x": Role("x", ["p"]), "y": Role("y", ["q"])}
        names, log = ["y", "x"], []
        authorize(roles, names, "p", log)
        names.append("z")
        self.assertEqual(log, [{"action": "p", "allowed": True, "roles": ["x", "y"]}])


if __name__ == "__main__":
    unittest.main()
