import unittest

from scheduler import TaskScheduler


class FakeClock:
    def __init__(self, now=0.0):
        self.now = now
        self.reads = 0

    def __call__(self):
        self.reads += 1
        return self.now


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.s = TaskScheduler(self.clock)

    def drain(self):
        out = []
        while (t := self.s.pop_due()) is not None:
            out.append(t)
        return out

    def test_empty(self):
        self.assertIsNone(self.s.pop_due())
        self.assertEqual(self.s.pop_all_due(), [])
        self.assertIsNone(self.s.seconds_until_next())
        self.assertEqual(len(self.s), 0)
        self.assertNotIn("a", self.s)

    def test_due_boundary_is_inclusive(self):
        self.s.schedule("a", 10)
        self.clock.now = 9.9
        self.assertIsNone(self.s.pop_due())
        self.assertEqual(len(self.s), 1)
        self.clock.now = 10
        self.assertEqual(self.s.pop_due(), "a")
        self.assertEqual(len(self.s), 0)
        self.assertIsNone(self.s.pop_due())

    def test_priority_higher_first(self):
        self.s.schedule("a", 0, priority=1)
        self.s.schedule("b", 0, priority=5)
        self.s.schedule("c", 0, priority=3)
        self.s.schedule("d", 0)
        self.s.schedule("e", 0, priority=-2)
        self.clock.now = 1
        self.assertEqual(self.drain(), ["b", "c", "a", "d", "e"])

    def test_ties_by_run_at_then_insertion(self):
        self.s.schedule("x", 5)
        self.s.schedule("y", 3)
        self.s.schedule("z", 3)
        self.s.schedule("w", 4)
        self.clock.now = 10
        self.assertEqual(self.drain(), ["y", "z", "w", "x"])

    def test_priority_beats_run_at(self):
        self.s.schedule("early_low", 1, priority=0)
        self.s.schedule("late_high", 8, priority=9)
        self.clock.now = 10
        self.assertEqual(self.drain(), ["late_high", "early_low"])

    def test_not_due_high_priority_does_not_block(self):
        self.s.schedule("hi", 100, priority=9)
        self.s.schedule("lo", 1, priority=0)
        self.clock.now = 50
        self.assertEqual(self.s.pop_due(), "lo")
        self.assertIsNone(self.s.pop_due())
        self.clock.now = 100
        self.assertEqual(self.s.pop_due(), "hi")

    def test_tasks_becoming_due_between_pops(self):
        self.s.schedule("a", 5, priority=1)
        self.clock.now = 5
        self.assertEqual(self.s.pop_due(), "a")
        self.s.schedule("b", 6, priority=1)
        self.s.schedule("c", 7, priority=9)
        self.clock.now = 6
        self.assertEqual(self.s.pop_due(), "b")
        self.assertIsNone(self.s.pop_due())
        self.clock.now = 7
        self.assertEqual(self.s.pop_due(), "c")

    def test_duplicate_schedule_rejected(self):
        self.s.schedule("a", 1, priority=2)
        with self.assertRaises(ValueError):
            self.s.schedule("a", 99, priority=7)
        self.assertEqual(len(self.s), 1)
        self.assertEqual(self.s.run_at_of("a"), 1)
        self.clock.now = 1
        self.assertEqual(self.s.pop_due(), "a")
        self.s.schedule("a", 2)  # allowed again after being popped
        self.assertIn("a", self.s)

    def test_cancel(self):
        self.s.schedule("a", 1)
        self.s.schedule("b", 2)
        self.assertTrue(self.s.cancel("a"))
        self.assertFalse(self.s.cancel("a"))
        self.assertFalse(self.s.cancel("nope"))
        self.assertEqual(len(self.s), 1)
        self.assertNotIn("a", self.s)
        self.clock.now = 10
        self.assertEqual(self.drain(), ["b"])

    def test_cancel_then_schedule_same_id_later(self):
        self.s.schedule("a", 1, priority=5)
        self.assertTrue(self.s.cancel("a"))
        self.s.schedule("a", 20, priority=0)
        self.clock.now = 5
        self.assertIsNone(self.s.pop_due())  # the stale entry must not fire
        self.clock.now = 20
        self.assertEqual(self.s.pop_due(), "a")
        self.assertIsNone(self.s.pop_due())

    def test_cancel_a_due_task(self):
        self.s.schedule("a", 0, priority=9)
        self.s.schedule("b", 0, priority=1)
        self.clock.now = 1
        self.assertEqual(self.s.seconds_until_next(), 0.0)  # a and b are due now
        self.assertTrue(self.s.cancel("a"))
        self.assertEqual(self.s.pop_due(), "b")
        self.assertIsNone(self.s.pop_due())

    def test_reschedule_into_future_and_past(self):
        self.s.schedule("a", 1)
        self.s.schedule("b", 50)
        self.clock.now = 10
        self.s.reschedule("a", 30)  # was due, now is not
        self.assertIsNone(self.s.pop_due())
        self.assertEqual(self.s.run_at_of("a"), 30)
        self.s.reschedule("b", 5)  # now overdue
        self.assertEqual(self.s.pop_due(), "b")
        self.clock.now = 30
        self.assertEqual(self.s.pop_due(), "a")

    def test_reschedule_after_task_was_promoted(self):
        self.s.schedule("a", 1, priority=3)
        self.s.schedule("b", 1, priority=1)
        self.clock.now = 2
        self.assertEqual(self.s.pop_due(), "a")  # b has been looked at and is due
        self.s.reschedule("b", 40)
        self.assertIsNone(self.s.pop_due())
        self.assertEqual(self.s.seconds_until_next(), 38)
        self.clock.now = 40
        self.assertEqual(self.s.pop_due(), "b")

    def test_reschedule_priority(self):
        self.s.schedule("a", 0, priority=1)
        self.s.schedule("b", 0, priority=2)
        self.s.reschedule("a", 0)  # priority kept
        self.clock.now = 1
        self.assertEqual(self.s.pop_due(), "b")
        self.s.schedule("c", 0, priority=0)
        self.s.reschedule("c", 0, priority=10)
        self.assertEqual(self.drain(), ["c", "a"])

    def test_reschedule_keeps_insertion_order(self):
        self.s.schedule("a", 5)
        self.s.schedule("b", 5)
        self.s.reschedule("a", 5)
        self.s.reschedule("a", 7)
        self.s.reschedule("a", 5)
        self.clock.now = 9
        self.assertEqual(self.drain(), ["a", "b"])

    def test_reschedule_unknown(self):
        with self.assertRaises(KeyError):
            self.s.reschedule("ghost", 1)
        self.s.schedule("a", 1)
        self.clock.now = 1
        self.s.pop_due()
        with self.assertRaises(KeyError):
            self.s.reschedule("a", 5)
        with self.assertRaises(KeyError):
            self.s.run_at_of("a")

    def test_seconds_until_next(self):
        self.s.schedule("late", 30, priority=9)
        self.s.schedule("soon", 12, priority=0)
        self.clock.now = 10
        self.assertEqual(self.s.seconds_until_next(), 2)
        self.clock.now = 12
        self.assertEqual(self.s.seconds_until_next(), 0.0)
        self.clock.now = 25
        self.assertEqual(self.s.seconds_until_next(), 0.0)
        self.s.cancel("soon")
        self.assertEqual(self.s.seconds_until_next(), 5)
        self.s.cancel("late")
        self.assertIsNone(self.s.seconds_until_next())

    def test_seconds_until_next_does_not_consume(self):
        self.s.schedule("a", 1)
        self.clock.now = 5
        self.s.seconds_until_next()
        self.assertEqual(len(self.s), 1)
        self.assertEqual(self.s.pop_due(), "a")

    def test_pop_all_due(self):
        self.s.schedule("a", 1, priority=1)
        self.s.schedule("b", 2, priority=5)
        self.s.schedule("c", 99)
        self.s.schedule("d", 3, priority=5)
        self.clock.now = 10
        before = self.clock.reads
        self.assertEqual(self.s.pop_all_due(), ["b", "d", "a"])
        self.assertEqual(self.clock.reads - before, 1)
        self.assertEqual(len(self.s), 1)
        self.assertEqual(self.s.pop_all_due(), [])

    def test_non_string_ids_and_float_times(self):
        self.s.schedule(("job", 1), 0.5)
        self.s.schedule(42, 0.25)
        self.clock.now = 0.5
        self.assertEqual(self.drain(), [42, ("job", 1)])

    def test_many_tasks(self):
        n = 20000
        for i in range(n):
            self.s.schedule(i, float(i % 100), priority=i % 3)
        self.assertEqual(len(self.s), n)
        for i in range(0, n, 4):
            self.s.cancel(i)
        for i in range(1, n, 8):
            self.s.reschedule(i, 1000.0)
        self.clock.now = 99.0
        popped = self.s.pop_all_due()
        expected_total = len([i for i in range(n) if i % 4 != 0 and not (i % 8 == 1)])
        self.assertEqual(len(popped), expected_total)
        # order check: priority non-increasing; within equal priority run_at non-decreasing
        keys = [(-(i % 3), float(i % 100), i) for i in popped]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(len(self.s), len([i for i in range(1, n, 8)]))
        self.clock.now = 1000.0
        self.assertEqual(len(self.s.pop_all_due()), len(range(1, n, 8)))
        self.assertEqual(len(self.s), 0)


if __name__ == "__main__":
    unittest.main()
