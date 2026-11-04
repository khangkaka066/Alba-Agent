import unittest

from playlist import Playlist


class PlaylistFullTests(unittest.TestCase):
    def test_instances_are_independent(self):
        a = Playlist("a")
        b = Playlist("b")
        a.add("song", 100)
        self.assertEqual(len(a), 1)
        self.assertEqual(len(b), 0)
        self.assertEqual(b.total_seconds(), 0)

    def test_new_instance_starts_empty_after_others_used(self):
        first = Playlist("first")
        first.add("one", 10)
        first.add("two", 20)
        second = Playlist("second")
        self.assertEqual(len(second), 0)
        self.assertEqual(second.duration_label(), "0:00")

    def test_from_pairs_independent(self):
        a = Playlist.from_pairs("a", [("x", 60), ("y", 65)])
        b = Playlist.from_pairs("b", [("z", 5)])
        self.assertEqual(len(a), 2)
        self.assertEqual(len(b), 1)
        self.assertEqual(a.total_seconds(), 125)
        self.assertEqual(b.total_seconds(), 5)

    def test_remove(self):
        a = Playlist.from_pairs("a", [("x", 1), ("y", 2), ("x", 3)])
        b = Playlist("b")
        self.assertTrue(a.remove("x"))
        self.assertEqual(a.tracks, [("y", 2), ("x", 3)])
        self.assertFalse(b.remove("x"))
        self.assertEqual(len(b), 0)

    def test_remove_missing(self):
        a = Playlist.from_pairs("a", [("x", 1)])
        self.assertFalse(a.remove("nope"))
        self.assertEqual(len(a), 1)

    def test_duration_label(self):
        self.assertEqual(Playlist.from_pairs("p", [("a", 3725)]).duration_label(), "62:05")
        self.assertEqual(Playlist.from_pairs("p", [("a", 59), ("b", 1)]).duration_label(), "1:00")

    def test_names_kept(self):
        self.assertEqual(Playlist("mix").name, "mix")
        self.assertEqual(Playlist("other").name, "other")


if __name__ == "__main__":
    unittest.main()
