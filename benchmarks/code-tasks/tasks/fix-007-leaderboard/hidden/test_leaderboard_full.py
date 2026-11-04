import unittest

from leaderboard import rank_players, sort_players, top_names


class LeaderboardFullTests(unittest.TestCase):
    def test_sort_by_score_desc(self):
        self.assertEqual(sort_players([("a", 1), ("b", 3), ("c", 2)]), [("b", 3), ("c", 2), ("a", 1)])

    def test_ties_alphabetical(self):
        players = [("bob", 10), ("amy", 10), ("cal", 7)]
        self.assertEqual(sort_players(players), [("amy", 10), ("bob", 10), ("cal", 7)])

    def test_ties_ignore_case(self):
        players = [("bob", 5), ("Amy", 5), ("carl", 5), ("Bea", 5)]
        self.assertEqual([n for n, _ in sort_players(players)], ["Amy", "Bea", "bob", "carl"])

    def test_negative_and_float_scores(self):
        players = [("a", -1), ("b", 2.5), ("c", -1), ("d", 0)]
        self.assertEqual([n for n, _ in sort_players(players)], ["b", "d", "a", "c"])

    def test_does_not_modify_input(self):
        players = [("b", 1), ("a", 2)]
        sort_players(players)
        self.assertEqual(players, [("b", 1), ("a", 2)])

    def test_competition_ranking(self):
        players = [("d", 7), ("a", 10), ("b", 10), ("c", 10), ("e", 1)]
        self.assertEqual(
            rank_players(players),
            [(1, "a", 10), (1, "b", 10), (1, "c", 10), (4, "d", 7), (5, "e", 1)],
        )

    def test_rank_no_ties(self):
        self.assertEqual(rank_players([("x", 1), ("y", 2)]), [(1, "y", 2), (2, "x", 1)])

    def test_top_names(self):
        players = [("bob", 10), ("amy", 10), ("cal", 7)]
        self.assertEqual(top_names(players, 2), ["amy", "bob"])
        self.assertEqual(top_names(players, 10), ["amy", "bob", "cal"])
        self.assertEqual(top_names([], 3), [])


if __name__ == "__main__":
    unittest.main()
