import unittest

from convert import NoConversion, UnknownUnit, convert, default_registry, factor
from registry import UnitRegistry


class ConvertHiddenTests(unittest.TestCase):
    def setUp(self):
        self.reg = default_registry()

    def test_reverse_relations(self):
        self.assertAlmostEqual(factor(self.reg, "m", "km"), 0.001)
        self.assertAlmostEqual(factor(self.reg, "cm", "in"), 1 / 2.54)
        self.assertAlmostEqual(factor(self.reg, "oz", "lb"), 1 / 16)

    def test_chains_in_both_directions(self):
        self.assertAlmostEqual(convert(self.reg, 1, "mi", "km"), 1.609344)
        self.assertAlmostEqual(convert(self.reg, 1609.344, "m", "mi"), 1)
        self.assertAlmostEqual(convert(self.reg, 3, "yd", "in"), 108)
        self.assertAlmostEqual(convert(self.reg, 36, "in", "yd"), 1)
        self.assertAlmostEqual(convert(self.reg, 10, "mm", "ft"), 10 / 304.8)

    def test_round_trip_is_identity(self):
        for a, b in [("km", "mm"), ("mi", "cm"), ("yd", "m"), ("kg", "g"), ("lb", "oz")]:
            self.assertAlmostEqual(convert(self.reg, convert(self.reg, 7.5, a, b), b, a), 7.5, places=9)
            self.assertAlmostEqual(factor(self.reg, a, b) * factor(self.reg, b, a), 1.0, places=9)

    def test_same_unit(self):
        self.assertEqual(factor(self.reg, "m", "m"), 1.0)
        self.assertEqual(convert(self.reg, 4.25, "kg", "kg"), 4.25)

    def test_unrelated_and_unknown(self):
        with self.assertRaises(NoConversion):
            factor(self.reg, "kg", "m")
        with self.assertRaises(UnknownUnit):
            factor(self.reg, "m", "furlong")
        with self.assertRaises(UnknownUnit):
            factor(self.reg, "furlong", "m")

    def test_registry_neighbours_both_ways(self):
        reg = UnitRegistry()
        reg.add("a", "b", 4)
        self.assertEqual(reg.neighbours("a"), [("b", 4)])
        self.assertEqual(reg.neighbours("b"), [("a", 0.25)])
        self.assertIn("b", reg)
        self.assertNotIn("c", reg)

    def test_registry_rejects_bad_factor(self):
        with self.assertRaises(ValueError):
            UnitRegistry().add("a", "b", 0)

    def test_fewest_steps_is_preferred(self):
        reg = UnitRegistry()
        reg.add("a", "b", 2)
        reg.add("b", "c", 2)
        reg.add("a", "c", 10)  # direct, one step, wins over a-b-c (factor 4)
        self.assertAlmostEqual(factor(reg, "a", "c"), 10)
        self.assertAlmostEqual(factor(reg, "c", "a"), 0.1)

    def test_custom_chain_with_non_integer_factors(self):
        reg = UnitRegistry()
        reg.add("pound", "shilling", 20)
        reg.add("shilling", "pence", 12)
        reg.add("guinea", "shilling", 21)
        self.assertAlmostEqual(convert(reg, 1, "guinea", "pence"), 252)
        self.assertAlmostEqual(convert(reg, 252, "pence", "pound"), 1.05)


if __name__ == "__main__":
    unittest.main()
