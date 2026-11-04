import unittest

from access import admit, can_enter


def person(name, age, ticket, vip):
    return {"name": name, "age": age, "ticket": ticket, "vip": vip}


class AccessTests(unittest.TestCase):
    def test_minor_vip_is_turned_away(self):
        crowd = [person("ann", 30, True, False), person("kid", 15, False, True)]
        self.assertEqual(admit(crowd), ["ann"])

    def test_minor_vip_direct(self):
        self.assertFalse(can_enter(17, False, True))

    def test_adult_vip_without_ticket(self):
        self.assertEqual(admit([person("vic", 40, False, True)]), ["vic"])


if __name__ == "__main__":
    unittest.main()
