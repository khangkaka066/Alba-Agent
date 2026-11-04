import unittest

from sessions import SessionStore


class SessionFullTests(unittest.TestCase):
    def make(self):
        store = SessionStore(ttl=10)
        store.create("a", 0)
        store.create("b", 5)
        store.create("c", 12)
        return store

    def test_purge_removes_expired(self):
        store = self.make()
        self.assertEqual(store.purge(15), ["a", "b"])
        self.assertEqual(store.active_count(15), 1)
        self.assertTrue(store.is_active("c", 15))

    def test_purge_is_idempotent(self):
        store = self.make()
        store.purge(15)
        self.assertEqual(store.purge(15), [])

    def test_purge_nothing_expired(self):
        store = self.make()
        self.assertEqual(store.purge(9), [])
        self.assertEqual(store.active_count(9), 3)

    def test_purge_everything(self):
        store = self.make()
        self.assertEqual(store.purge(100), ["a", "b", "c"])
        self.assertEqual(store.active_count(100), 0)

    def test_expiry_boundary(self):
        store = SessionStore(ttl=10)
        store.create("a", 0)
        self.assertTrue(store.is_active("a", 9))
        self.assertFalse(store.is_active("a", 10))

    def test_touch_extends_live_session(self):
        store = SessionStore(ttl=10)
        store.create("a", 0)
        self.assertTrue(store.touch("a", 8))
        self.assertTrue(store.is_active("a", 17))
        self.assertFalse(store.is_active("a", 18))

    def test_expired_session_cannot_be_touched_back(self):
        store = SessionStore(ttl=10)
        store.create("a", 0)
        self.assertFalse(store.touch("a", 15))
        self.assertFalse(store.is_active("a", 15))
        self.assertFalse(store.touch("a", 16))
        self.assertEqual(store.purge(16), ["a"])

    def test_touch_at_exact_expiry_is_too_late(self):
        store = SessionStore(ttl=10)
        store.create("a", 0)
        self.assertFalse(store.touch("a", 10))

    def test_touch_unknown(self):
        store = SessionStore(ttl=10)
        self.assertFalse(store.touch("ghost", 1))
        self.assertFalse(store.is_active("ghost", 1))

    def test_create_restarts_expired_session(self):
        store = SessionStore(ttl=10)
        store.create("a", 0)
        store.create("a", 20)
        self.assertTrue(store.is_active("a", 25))


if __name__ == "__main__":
    unittest.main()
