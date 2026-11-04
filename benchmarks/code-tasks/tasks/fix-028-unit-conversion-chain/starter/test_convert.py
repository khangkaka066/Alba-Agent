import unittest

from convert import convert, default_registry


class ConvertTests(unittest.TestCase):
    def setUp(self):
        self.reg = default_registry()

    def test_forward(self):
        self.assertAlmostEqual(convert(self.reg, 2, "km", "m"), 2000)
        self.assertAlmostEqual(convert(self.reg, 1, "ft", "cm"), 30.48)

    def test_reverse(self):
        self.assertAlmostEqual(convert(self.reg, 500, "m", "km"), 0.5)

    def test_long_chain_downwards(self):
        self.assertAlmostEqual(convert(self.reg, 1, "mi", "m"), 1609.344)


if __name__ == "__main__":
    unittest.main()
