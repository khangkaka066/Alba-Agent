import unittest

from sessions import SessionStore


class SessionTests(unittest.TestCase):
    def test_purge_removes_expired(self):
        store = SessionStore(ttl=10)
        store.create("a", 0)
        store.create("b", 5)
        store.create("c", 12)
        self.assertEqual(store.purge(15), ["a", "b"])
        self.assertEqual(store.active_count(15), 1)

    def test_expired_session_cannot_be_touched_back(self):
        store = SessionStore(ttl=10)
        store.create("a", 0)
        self.assertFalse(store.touch("a", 15))
        self.assertFalse(store.is_active("a", 15))


if __name__ == "__main__":
    unittest.main()
