import unittest

from team import Team


class TeamTests(unittest.TestCase):
    def test_teams_do_not_share_roles(self):
        a = Team("a")
        b = Team("b")
        a.add_role("lead")
        self.assertEqual(b.roles, [])
        self.assertEqual(a.roles, ["lead"])


if __name__ == "__main__":
    unittest.main()
