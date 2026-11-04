import unittest

from acl.audit import authorize
from acl.policy import can, matches
from acl.roles import Role, effective_perms


def roles_of(*items):
    return {role.name: role for role in items}


class RolesTests(unittest.TestCase):
    def test_inheritance(self):
        roles = roles_of(Role("base", ["read"]), Role("editor", ["write"], ["base"]), Role("admin", ["admin:*"], ["editor"]))
        self.assertEqual(effective_perms(roles, "admin"), {"admin:*", "write", "read"})
        self.assertEqual(effective_perms(roles, "editor"), {"write", "read"})
        self.assertEqual(effective_perms(roles, "base"), {"read"})

    def test_returns_a_new_set(self):
        roles = roles_of(Role("a", ["x"]))
        effective_perms(roles, "a").add("y")
        self.assertEqual(roles["a"].perms, {"x"})

    def test_diamond_is_not_a_cycle(self):
        roles = roles_of(Role("top", ["t"]), Role("l", ["a"], ["top"]), Role("r", ["b"], ["top"]), Role("bottom", ["c"], ["l", "r"]))
        self.assertEqual(effective_perms(roles, "bottom"), {"t", "a", "b", "c"})

    def test_cycles(self):
        for roles, start in [
            (roles_of(Role("a", parents=["b"]), Role("b", parents=["a"])), "a"),
            (roles_of(Role("a", parents=["a"])), "a"),
            (roles_of(Role("x", parents=["a"]), Role("a", parents=["b"]), Role("b", parents=["c"]), Role("c", parents=["a"])), "x"),
        ]:
            with self.assertRaises(ValueError):
                effective_perms(roles, start)

    def test_unknown_roles(self):
        roles = roles_of(Role("a", parents=["ghost"]))
        with self.assertRaises(KeyError) as caught:
            effective_perms(roles, "a")
        self.assertEqual(caught.exception.args, ("ghost",))
        with self.assertRaises(KeyError) as caught:
            effective_perms(roles, "nobody")
        self.assertEqual(caught.exception.args, ("nobody",))


class PolicyTests(unittest.TestCase):
    def test_matches(self):
        self.assertTrue(matches("*", "anything"))
        self.assertTrue(matches("doc:*", "doc:read"))
        self.assertTrue(matches("doc:*", "doc:"))
        self.assertFalse(matches("doc:*", "docs:read"))
        self.assertTrue(matches("doc:read", "doc:read"))
        self.assertFalse(matches("doc:read", "doc:read:all"))
        self.assertFalse(matches("a*b", "axb"))
        self.assertTrue(matches("a*b", "a*b"))

    def test_deny_wins_in_any_order(self):
        self.assertFalse(can(["doc:*", "!doc:delete"], "doc:delete"))
        self.assertFalse(can(["!doc:delete", "doc:*"], "doc:delete"))
        self.assertTrue(can(["!doc:delete", "doc:*"], "doc:read"))
        self.assertFalse(can(["*", "!*"], "x"))
        self.assertFalse(can({"x", "!x"}, "x"))

    def test_nothing_matches_means_denied(self):
        self.assertFalse(can([], "x"))
        self.assertFalse(can(["y"], "x"))
        self.assertFalse(can(["!x"], "x"))
        self.assertFalse(can(["!y"], "x"))

    def test_accepts_any_iterable(self):
        self.assertTrue(can((p for p in ["a:*"]), "a:b"))


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.roles = roles_of(Role("reader", ["doc:read"]), Role("writer", ["doc:write", "!doc:delete"], ["reader"]),
                              Role("ops", ["doc:*"]))

    def test_union_of_roles_with_deny(self):
        self.assertTrue(authorize(self.roles, ["writer"], "doc:read"))
        self.assertTrue(authorize(self.roles, ["writer"], "doc:write"))
        self.assertFalse(authorize(self.roles, ["writer"], "doc:delete"))
        self.assertFalse(authorize(self.roles, ["writer", "ops"], "doc:delete"))
        self.assertTrue(authorize(self.roles, ["ops"], "doc:delete"))

    def test_no_roles(self):
        self.assertFalse(authorize(self.roles, [], "doc:read"))

    def test_unknown_role(self):
        with self.assertRaises(KeyError):
            authorize(self.roles, ["reader", "ghost"], "doc:read")

    def test_log_entries(self):
        log = []
        names = ["writer", "ops"]
        authorize(self.roles, names, "doc:delete", log)
        authorize(self.roles, ["reader"], "doc:read", log)
        names.append("changed")
        names.reverse()
        self.assertEqual(log, [
            {"action": "doc:delete", "allowed": False, "roles": ["ops", "writer"]},
            {"action": "doc:read", "allowed": True, "roles": ["reader"]},
        ])

    def test_no_log_argument_is_fine(self):
        self.assertTrue(authorize(self.roles, ["reader"], "doc:read"))


if __name__ == "__main__":
    unittest.main()
