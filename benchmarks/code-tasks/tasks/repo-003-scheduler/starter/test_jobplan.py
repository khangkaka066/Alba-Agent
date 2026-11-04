import unittest

from jobplan.model import Job
from jobplan.order import CycleError, execution_order
from jobplan.timeparse import parse_duration


class SchedTests(unittest.TestCase):
    def test_durations(self):
        self.assertEqual(parse_duration("1h30m"), 5400)
        self.assertEqual(parse_duration("90"), 90)
        with self.assertRaises(ValueError):
            parse_duration("abc")

    def test_order_is_alphabetical_among_ready_jobs(self):
        jobs = {"b": Job("b", 1), "c": Job("c", 1), "a": Job("a", 1, ["b"])}
        self.assertEqual(execution_order(jobs), ["b", "a", "c"])

    def test_cycle(self):
        jobs = {"a": Job("a", 1, ["b"]), "b": Job("b", 1, ["a"])}
        with self.assertRaises(CycleError):
            execution_order(jobs)


if __name__ == "__main__":
    unittest.main()
