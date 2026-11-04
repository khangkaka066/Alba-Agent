import random
import unittest

from jobs import JobQueue


class Boom(Exception):
    pass


class JobsHiddenTests(unittest.TestCase):
    def test_snapshot_is_a_copy(self):
        q = JobQueue()
        q.push(1)
        q.push(2)
        snap = q.snapshot()
        snap.append(99)
        snap.clear()
        self.assertEqual(q.snapshot(), [1, 2])
        self.assertEqual(len(q), 2)

    def test_retry_after_failure_reprocesses_same_job_first(self):
        q = JobQueue()
        for i in range(3):
            q.push(i)
        attempts = {"n": 0}
        out = []

        def flaky(job):
            if job == 1 and attempts["n"] == 0:
                attempts["n"] += 1
                raise Boom
            out.append(job)

        with self.assertRaises(Boom):
            q.drain(flaky)
        self.assertEqual(out, [0])
        self.assertEqual(q.drain(flaky), 2)
        self.assertEqual(out, [0, 1, 2])
        self.assertEqual(q.processed, 3)

    def test_failure_when_handler_pushed_jobs(self):
        q = JobQueue()
        q.push("a")
        q.push("b")

        def handler(job):
            if job == "a":
                q.push("c")
            if job == "b":
                q.push("d")
                raise Boom

        with self.assertRaises(Boom):
            q.drain(handler)
        self.assertEqual(q.snapshot(), ["b", "c", "d"])

    def test_handler_pushes_are_handled_in_same_drain(self):
        q = JobQueue()
        q.push(3)
        seen = []

        def handler(n):
            seen.append(n)
            if n > 0:
                q.push(n - 1)

        self.assertEqual(q.drain(handler), 4)
        self.assertEqual(seen, [3, 2, 1, 0])

    def test_limit_and_processed(self):
        q = JobQueue()
        for i in range(5):
            q.push(i)
        out = []
        self.assertEqual(q.drain(out.append, limit=2), 2)
        self.assertEqual(q.drain(out.append, limit=0), 0)
        self.assertEqual(q.snapshot(), [2, 3, 4])
        self.assertEqual(q.drain(out.append, limit=10), 3)
        self.assertEqual(q.processed, 5)
        self.assertEqual(q.drain(out.append), 0)

    def test_failure_does_not_count_and_pop(self):
        q = JobQueue()
        q.push("x")

        def bad(job):
            raise Boom

        for _ in range(3):
            with self.assertRaises(Boom):
                q.drain(bad)
        self.assertEqual(q.processed, 0)
        self.assertEqual(q.pop(), "x")
        with self.assertRaises(IndexError):
            q.pop()

    def test_exception_type_propagates_unchanged(self):
        q = JobQueue()
        q.push(1)
        err = Boom("specific")

        def bad(job):
            raise err

        with self.assertRaises(Boom) as cm:
            q.drain(bad)
        self.assertIs(cm.exception, err)

    def test_random_sequences_match_model(self):
        rng = random.Random(1234)
        for _ in range(30):
            q = JobQueue()
            model = []
            processed = 0
            counter = 0
            for _ in range(200):
                op = rng.choice(["push", "push", "pop", "drain", "snap"])
                if op == "push":
                    q.push(counter)
                    model.append(counter)
                    counter += 1
                elif op == "pop":
                    if model:
                        self.assertEqual(q.pop(), model.pop(0))
                    else:
                        with self.assertRaises(IndexError):
                            q.pop()
                elif op == "snap":
                    s = q.snapshot()
                    self.assertEqual(s, model)
                    s.append("junk")
                else:
                    limit = rng.choice([None, 0, 1, 3, 10])
                    fail_at = rng.choice([None, 0, 1, 2, 5])
                    spawn_at = rng.choice([None, 0, 1])
                    new_id = counter
                    spawned = []
                    calls = {"n": 0}

                    def handler(job, calls=calls, fail_at=fail_at, spawn_at=spawn_at):
                        i = calls["n"]
                        calls["n"] += 1
                        if i == spawn_at:
                            q.push(("s", job))
                        if i == fail_at:
                            raise Boom

                    # model
                    m_handled = 0
                    m_fail = False
                    m_calls = 0
                    while model and (limit is None or m_handled < limit):
                        job = model[0]
                        i = m_calls
                        m_calls += 1
                        if i == spawn_at:
                            model.append(("s", job))
                        if i == fail_at:
                            m_fail = True
                            break
                        model.pop(0)
                        m_handled += 1
                        processed += 1
                    if m_fail:
                        with self.assertRaises(Boom):
                            q.drain(handler, limit)
                    else:
                        self.assertEqual(q.drain(handler, limit), m_handled)
                self.assertEqual(q.snapshot(), model)
                self.assertEqual(len(q), len(model))
                self.assertEqual(q.processed, processed)


if __name__ == "__main__":
    unittest.main()
