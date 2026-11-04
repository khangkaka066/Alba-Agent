import unittest

from ringbuf import RingBuffer


class RingBufferTests(unittest.TestCase):
    def test_invalid_capacity(self):
        for bad in (0, -3):
            with self.assertRaises(ValueError):
                RingBuffer(bad)

    def test_fill_without_overwrite(self):
        buf = RingBuffer(3)
        self.assertFalse(buf)
        self.assertFalse(buf.push(1))
        self.assertFalse(buf.push(2))
        self.assertFalse(buf.is_full())
        self.assertFalse(buf.push(3))
        self.assertTrue(buf.is_full())
        self.assertEqual(len(buf), 3)
        self.assertEqual(buf.to_list(), [1, 2, 3])
        self.assertEqual(buf.dropped, 0)

    def test_overwrite_discards_oldest(self):
        buf = RingBuffer(3)
        for i in range(1, 6):
            buf.push(i)
        self.assertEqual(buf.to_list(), [3, 4, 5])
        self.assertEqual(buf.dropped, 2)
        self.assertTrue(buf.push(6))
        self.assertEqual(list(buf), [4, 5, 6])
        self.assertEqual(buf.dropped, 3)

    def test_indexing(self):
        buf = RingBuffer(3)
        for i in range(10, 15):
            buf.push(i)
        self.assertEqual([buf[0], buf[1], buf[2]], [12, 13, 14])
        self.assertEqual(buf[-1], 14)
        self.assertEqual(buf[-3], 12)
        for bad in (3, -4):
            with self.assertRaises(IndexError):
                buf[bad]

    def test_pop_and_peek(self):
        buf = RingBuffer(3)
        for i in range(5):
            buf.push(i)
        self.assertEqual(buf.peek_oldest(), 2)
        self.assertEqual(buf.peek_newest(), 4)
        self.assertEqual(buf.pop_oldest(), 2)
        self.assertEqual(buf.to_list(), [3, 4])
        self.assertFalse(buf.push(5))  # room was made by the pop
        self.assertEqual(buf.dropped, 2)
        self.assertEqual(buf.to_list(), [3, 4, 5])
        self.assertEqual([buf.pop_oldest() for _ in range(3)], [3, 4, 5])
        self.assertEqual(len(buf), 0)

    def test_empty_errors(self):
        buf = RingBuffer(2)
        for call in (buf.pop_oldest, buf.peek_oldest, buf.peek_newest):
            with self.assertRaises(IndexError):
                call()
        buf.push("x")
        buf.pop_oldest()
        with self.assertRaises(IndexError):
            buf.pop_oldest()

    def test_latest(self):
        buf = RingBuffer(5)
        for i in range(1, 8):
            buf.push(i)
        self.assertEqual(buf.latest(2), [6, 7])
        self.assertEqual(buf.latest(5), [3, 4, 5, 6, 7])
        self.assertEqual(buf.latest(99), [3, 4, 5, 6, 7])
        self.assertEqual(buf.latest(0), [])
        with self.assertRaises(ValueError):
            buf.latest(-1)

    def test_clear_keeps_dropped(self):
        buf = RingBuffer(2)
        for i in range(4):
            buf.push(i)
        buf.clear()
        self.assertEqual(len(buf), 0)
        self.assertEqual(buf.to_list(), [])
        self.assertEqual(buf.dropped, 2)
        buf.push("a")
        self.assertEqual(buf.to_list(), ["a"])

    def test_none_items_and_to_list_is_copy(self):
        buf = RingBuffer(2)
        buf.push(None)
        buf.push(None)
        self.assertEqual(len(buf), 2)
        self.assertTrue(buf.is_full())
        self.assertIsNone(buf.peek_oldest())
        snapshot = buf.to_list()
        snapshot.append("junk")
        self.assertEqual(len(buf.to_list()), 2)

    def test_capacity_one(self):
        buf = RingBuffer(1)
        self.assertFalse(buf.push("a"))
        self.assertTrue(buf.push("b"))
        self.assertEqual(buf.to_list(), ["b"])
        self.assertEqual(buf.capacity, 1)


if __name__ == "__main__":
    unittest.main()
