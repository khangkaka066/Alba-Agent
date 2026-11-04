import unittest

from leaderboard import rank_players, top_names


class LeaderboardTests(unittest.TestCase):
    def test_tie_ranks(self):
        players = [("bob", 10), ("amy", 10), ("cal", 7)]
        self.assertEqual(rank_players(players), [(1, "amy", 10), (1, "bob", 10), (3, "cal", 7)])

    def test_top_names(self):
        players = [("bob", 10), ("amy", 10), ("cal", 7)]
        self.assertEqual(top_names(players, 2), ["amy", "bob"])


if __name__ == "__main__":
    unittest.main()
