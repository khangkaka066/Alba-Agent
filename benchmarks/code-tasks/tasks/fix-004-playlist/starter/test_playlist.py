import unittest

from playlist import Playlist


class PlaylistTests(unittest.TestCase):
    def test_instances_are_independent(self):
        a = Playlist("a")
        b = Playlist("b")
        a.add("song", 100)
        self.assertEqual(len(a), 1)
        self.assertEqual(len(b), 0)

    def test_total(self):
        p = Playlist.from_pairs("p", [("x", 60), ("y", 65)])
        self.assertEqual(p.total_seconds(), 125)


if __name__ == "__main__":
    unittest.main()
