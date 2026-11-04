import unittest

from leaderboard import top


class BoardTests(unittest.TestCase):
    def test_ties_keep_submission_order(self):
        entries = [("amy", 5), ("bob", 5), ("cat", 9)]
        self.assertEqual(top(entries, 3), [("cat", 9), ("amy", 5), ("bob", 5)])


if __name__ == "__main__":
    unittest.main()
