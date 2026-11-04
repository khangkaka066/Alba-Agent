import unittest

from jobs import JobQueue


class JobTests(unittest.TestCase):
    def test_drain_in_order(self):
        q = JobQueue()
        for i in range(3):
            q.push(i)
        out = []
        self.assertEqual(q.drain(out.append), 3)
        self.assertEqual(out, [0, 1, 2])
        self.assertEqual(len(q), 0)

    def test_failed_job_stays_at_front(self):
        q = JobQueue()
        for i in range(4):
            q.push(i)

        def handler(job):
            if job == 2:
                raise RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            q.drain(handler)
        self.assertEqual(q.snapshot(), [2, 3])
        self.assertEqual(q.processed, 2)


if __name__ == "__main__":
    unittest.main()
