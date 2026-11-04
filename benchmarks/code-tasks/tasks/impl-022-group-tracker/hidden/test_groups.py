import unittest

from groups import GroupTracker


class GroupTrackerTests(unittest.TestCase):
    def test_empty(self):
        t = GroupTracker()
        self.assertEqual(len(t), 0)
        self.assertEqual(t.group_count, 0)
        self.assertEqual(t.groups(), [])

    def test_add_is_idempotent(self):
        t = GroupTracker()
        t.add("a")
        t.add("a")
        t.add("b")
        self.assertEqual(len(t), 2)
        self.assertEqual(t.group_count, 2)
        self.assertIn("a", t)
        self.assertNotIn("z", t)
        self.assertEqual(t.size_of("a"), 1)

    def test_union_return_values_and_autoadd(self):
        t = GroupTracker()
        self.assertTrue(t.union(1, 2))
        self.assertFalse(t.union(2, 1))
        self.assertTrue(t.union(3, 4))
        self.assertTrue(t.union(2, 3))
        self.assertFalse(t.union(1, 4))
        self.assertFalse(t.union(9, 9))
        self.assertEqual(len(t), 5)
        self.assertEqual(t.group_count, 2)
        self.assertEqual(t.size_of(4), 4)
        self.assertEqual(t.size_of(9), 1)

    def test_connected(self):
        t = GroupTracker()
        t.union("a", "b")
        t.union("c", "d")
        t.add("e")
        self.assertTrue(t.connected("a", "b"))
        self.assertTrue(t.connected("e", "e"))
        self.assertFalse(t.connected("a", "c"))
        t.union("b", "c")
        self.assertTrue(t.connected("a", "d"))

    def test_unknown_elements_raise_key_error(self):
        t = GroupTracker()
        t.add(1)
        for call in (
            lambda: t.connected(1, 2),
            lambda: t.connected(2, 1),
            lambda: t.connected(2, 2),
            lambda: t.size_of(2),
            lambda: t.members(2),
        ):
            with self.assertRaises(KeyError):
                call()
        self.assertEqual(len(t), 1)  # queries must not register anything

    def test_members_sorted(self):
        t = GroupTracker()
        for a, b in [(5, 3), (3, 9), (1, 2)]:
            t.union(a, b)
        self.assertEqual(t.members(9), [3, 5, 9])
        self.assertEqual(t.members(2), [1, 2])

    def test_groups_ordering(self):
        t = GroupTracker()
        t.union("pear", "apple")
        t.union("kiwi", "fig")
        t.add("banana")
        t.union("zed", "kiwi")
        self.assertEqual(
            t.groups(),
            [["apple", "pear"], ["banana"], ["fig", "kiwi", "zed"]],
        )
        self.assertEqual(t.group_count, 3)

    def test_groups_return_value_is_a_copy(self):
        t = GroupTracker()
        t.union(1, 2)
        t.groups()[0].append(99)
        self.assertEqual(t.groups(), [[1, 2]])

    def test_long_chain_no_recursion_problem(self):
        t = GroupTracker()
        n = 100_000
        for i in range(n):
            t.union(i, i + 1)
        self.assertEqual(t.group_count, 1)
        self.assertEqual(t.size_of(0), n + 1)
        self.assertTrue(t.connected(0, n))

    def test_long_chain_reverse_order(self):
        t = GroupTracker()
        n = 50_000
        for i in range(n, 0, -1):
            t.union(i, i - 1)
        self.assertTrue(t.connected(0, n))
        self.assertEqual(t.size_of(n // 2), n + 1)

    def test_long_chain_attached_under_newest_element(self):
        t = GroupTracker()
        n = 60_000
        for i in range(n):
            t.union(i + 1, i)  # each new element is first in the pair
        self.assertTrue(t.connected(0, n))
        self.assertEqual(t.size_of(0), n + 1)
        self.assertEqual(t.members(n)[:3], [0, 1, 2])

    def test_many_small_groups(self):
        t = GroupTracker()
        for i in range(0, 20_000, 2):
            t.union(i, i + 1)
        self.assertEqual(t.group_count, 10_000)
        groups = t.groups()
        self.assertEqual(groups[0], [0, 1])
        self.assertEqual(groups[-1], [19_998, 19_999])


if __name__ == "__main__":
    unittest.main()
