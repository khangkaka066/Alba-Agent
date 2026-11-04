import unittest

from jobplan.model import Job
from jobplan.order import CycleError, execution_order
from jobplan.plan import critical_path_seconds
from jobplan.runner import run_all
from jobplan.timeparse import parse_duration


class DurationTests(unittest.TestCase):
    def test_valid(self):
        for text, seconds in [("1h30m", 5400), ("45s", 45), ("2h", 7200), ("1h 5m 10s", 3910), ("90", 90),
                              ("  5m ", 300), ("0s", 0), ("10m 30s", 630), ("1h30s", 3630)]:
            self.assertEqual(parse_duration(text), seconds, text)

    def test_invalid(self):
        for text in ["", "  ", "5x", "10s1h", "1h1h", "abc", "1h abc", "h", "1.5h", "-5s", "5m 1h", "1h30"]:
            with self.assertRaises(ValueError, msg=repr(text)):
                parse_duration(text)

    def test_job_accepts_string_or_int(self):
        self.assertEqual(Job("a", "1m").seconds, 60)
        self.assertEqual(Job("a", 7).seconds, 7)


class OrderTests(unittest.TestCase):
    def test_alphabetical_among_ready(self):
        jobs = {"b": Job("b", 1), "c": Job("c", 1), "a": Job("a", 1, ["b"])}
        self.assertEqual(execution_order(jobs), ["b", "a", "c"])

    def test_diamond(self):
        jobs = {n: Job(n, 1, d) for n, d in [("d", ["b", "c"]), ("b", ["a"]), ("c", ["a"]), ("a", [])]}
        self.assertEqual(execution_order(jobs), ["a", "b", "c", "d"])

    def test_duplicate_deps_are_harmless(self):
        jobs = {"a": Job("a", 1), "b": Job("b", 1, ["a", "a"])}
        self.assertEqual(execution_order(jobs), ["a", "b"])

    def test_empty(self):
        self.assertEqual(execution_order({}), [])

    def test_cycles(self):
        for jobs in [
            {"a": Job("a", 1, ["b"]), "b": Job("b", 1, ["a"])},
            {"a": Job("a", 1, ["a"])},
            {"x": Job("x", 1), "a": Job("a", 1, ["b"]), "b": Job("b", 1, ["c"]), "c": Job("c", 1, ["a"])},
        ]:
            with self.assertRaises(CycleError):
                execution_order(jobs)

    def test_unknown_dependency(self):
        with self.assertRaises(KeyError) as caught:
            execution_order({"a": Job("a", 1, ["ghost"])})
        self.assertEqual(caught.exception.args, ("ghost",))


class RunnerTests(unittest.TestCase):
    def test_failure_skips_transitively(self):
        calls = []

        def ok(name):
            return lambda: calls.append(name)

        def boom():
            raise RuntimeError("x")

        jobs = {
            "a": Job("a", 1, action=ok("a")),
            "b": Job("b", 1, ["a"], boom),
            "c": Job("c", 1, ["b"], ok("c")),
            "d": Job("d", 1, ["c"], ok("d")),
            "e": Job("e", 1, ["a"], ok("e")),
            "f": Job("f", 1, ["d", "e"], ok("f")),
        }
        self.assertEqual(run_all(jobs), {"a": "ok", "b": "failed", "c": "skipped", "d": "skipped", "e": "ok", "f": "skipped"})
        self.assertEqual(calls, ["a", "e"])

    def test_all_ok(self):
        jobs = {"a": Job("a", 1), "b": Job("b", 1, ["a"])}
        self.assertEqual(run_all(jobs), {"a": "ok", "b": "ok"})


class PlanTests(unittest.TestCase):
    def test_critical_path(self):
        jobs = {
            "a": Job("a", "1m"),
            "b": Job("b", "30s", ["a"]),
            "c": Job("c", "2m", ["a"]),
            "d": Job("d", 10, ["b", "c"]),
            "e": Job("e", "10m"),
        }
        self.assertEqual(critical_path_seconds(jobs), 600)
        del jobs["e"]
        self.assertEqual(critical_path_seconds(jobs), 190)

    def test_empty(self):
        self.assertEqual(critical_path_seconds({}), 0)


if __name__ == "__main__":
    unittest.main()
