import copy
import unittest

import settings
from settings import DEFAULTS, build_settings
from team import Team


class Hidden(unittest.TestCase):
    def setUp(self):
        self.pristine = copy.deepcopy(DEFAULTS)

    def tearDown(self):
        self.assertEqual(settings.DEFAULTS, self.pristine)

    def test_caller_list_not_aliased_or_mutated(self):
        roles = ["lead"]
        t = Team("a", roles)
        t.add_role("dev")
        self.assertEqual(roles, ["lead"])
        self.assertEqual(t.roles, ["lead", "dev"])
        roles.append("ghost")
        self.assertEqual(t.roles, ["lead", "dev"])

    def test_empty_caller_list_not_aliased(self):
        roles = []
        t = Team("a", roles)
        t.add_role("x")
        self.assertEqual(roles, [])

    def test_default_roles_independent(self):
        a, b, c = Team("a"), Team("b"), Team("c")
        a.add_role("1")
        b.add_role("2")
        self.assertEqual((a.roles, b.roles, c.roles), (["1"], ["2"], []))

    def test_settings_do_not_mutate_defaults(self):
        s = build_settings({"locale": "fr"})
        self.assertEqual(s["locale"], "fr")
        self.assertEqual(DEFAULTS["locale"], "en")

    def test_nested_merge(self):
        s = build_settings({"limits": {"roles": 1}})
        self.assertEqual(s["limits"], {"members": 10, "roles": 1})
        self.assertEqual(DEFAULTS["limits"], {"members": 10, "roles": 5})

    def test_result_does_not_share_nested(self):
        s = build_settings()
        s["limits"]["roles"] = 99
        self.assertEqual(DEFAULTS["limits"]["roles"], 5)
        self.assertEqual(build_settings()["limits"]["roles"], 5)

    def test_overrides_not_mutated_or_shared(self):
        ov = {"limits": {"members": 3}, "extra": {"k": [1]}}
        before = copy.deepcopy(ov)
        s = build_settings(ov)
        s["limits"]["members"] = 4
        s["extra"]["k"].append(2)
        self.assertEqual(ov, before)

    def test_explicit_base_untouched(self):
        base = {"a": {"b": 1}}
        s = build_settings({"a": {"c": 2}}, base)
        self.assertEqual(s, {"a": {"b": 1, "c": 2}})
        self.assertEqual(base, {"a": {"b": 1}})

    def test_team_settings_isolated(self):
        a = Team("a", settings={"limits": {"roles": 1}})
        b = Team("b")
        a.add_role("x")
        self.assertFalse(a.can_add_role())
        self.assertTrue(b.can_add_role())
        b.settings["limits"]["roles"] = 0
        self.assertTrue(Team("c").can_add_role())


if __name__ == "__main__":
    unittest.main()
