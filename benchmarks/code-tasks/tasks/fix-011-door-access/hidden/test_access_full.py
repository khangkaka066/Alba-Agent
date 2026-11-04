import unittest

from access import admit, can_enter, door_summary


def person(name, age, ticket, vip):
    return {"name": name, "age": age, "ticket": ticket, "vip": vip}


class AccessFullTests(unittest.TestCase):
    def test_truth_table_adult(self):
        self.assertTrue(can_enter(30, True, False))
        self.assertTrue(can_enter(30, False, True))
        self.assertTrue(can_enter(30, True, True))
        self.assertFalse(can_enter(30, False, False))

    def test_truth_table_minor(self):
        self.assertFalse(can_enter(17, True, False))
        self.assertFalse(can_enter(17, False, True))
        self.assertFalse(can_enter(17, True, True))
        self.assertFalse(can_enter(17, False, False))

    def test_age_boundary(self):
        self.assertTrue(can_enter(18, True, False))
        self.assertFalse(can_enter(17, True, False))
        self.assertFalse(can_enter(0, False, True))

    def test_result_is_bool_like(self):
        self.assertIs(bool(can_enter(10, False, True)), False)

    def test_admit_order(self):
        crowd = [
            person("a", 20, True, False),
            person("b", 12, False, True),
            person("c", 25, False, True),
            person("d", 40, False, False),
            person("e", 18, True, True),
        ]
        self.assertEqual(admit(crowd), ["a", "c", "e"])

    def test_admit_empty(self):
        self.assertEqual(admit([]), [])

    def test_door_summary(self):
        crowd = [
            person("a", 20, True, False),
            person("b", 12, False, True),
            person("c", 25, False, False),
        ]
        self.assertEqual(door_summary(crowd), (1, ["b", "c"]))


if __name__ == "__main__":
    unittest.main()
