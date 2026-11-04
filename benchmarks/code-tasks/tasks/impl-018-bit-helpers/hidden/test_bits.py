import unittest

import bits


class BitsTests(unittest.TestCase):
    def test_popcount(self):
        self.assertEqual(bits.popcount(0), 0)
        self.assertEqual(bits.popcount(7), 3)
        self.assertEqual(bits.popcount(2**70 - 1), 70)
        self.assertEqual(bits.popcount(0b101000), 2)

    def test_is_power_of_two(self):
        self.assertEqual([n for n in range(0, 40) if bits.is_power_of_two(n)], [1, 2, 4, 8, 16, 32])
        self.assertFalse(bits.is_power_of_two(-4))
        self.assertFalse(bits.is_power_of_two(-1))
        self.assertTrue(bits.is_power_of_two(2**100))

    def test_next_power_of_two(self):
        self.assertEqual(bits.next_power_of_two(0), 1)
        self.assertEqual(bits.next_power_of_two(1), 1)
        self.assertEqual(bits.next_power_of_two(2), 2)
        self.assertEqual(bits.next_power_of_two(3), 4)
        self.assertEqual(bits.next_power_of_two(64), 64)
        self.assertEqual(bits.next_power_of_two(65), 128)
        self.assertEqual(bits.next_power_of_two(2**40 + 1), 2**41)

    def test_get_set_clear_toggle(self):
        self.assertEqual(bits.get_bit(0b1010, 1), 1)
        self.assertEqual(bits.get_bit(0b1010, 0), 0)
        self.assertEqual(bits.get_bit(0b1010, 50), 0)
        self.assertEqual(bits.set_bit(0b1010, 0), 0b1011)
        self.assertEqual(bits.set_bit(0b1010, 1), 0b1010)
        self.assertEqual(bits.set_bit(0, 10), 1024)
        self.assertEqual(bits.clear_bit(0b1010, 1), 0b1000)
        self.assertEqual(bits.clear_bit(0b1010, 0), 0b1010)
        self.assertEqual(bits.clear_bit(5, 99), 5)
        self.assertEqual(bits.toggle_bit(0b1010, 0), 0b1011)
        self.assertEqual(bits.toggle_bit(0b1010, 3), 0b0010)

    def test_extract_bits(self):
        self.assertEqual(bits.extract_bits(0b11010110, 2, 3), 0b101)
        self.assertEqual(bits.extract_bits(0b11010110, 0, 4), 0b0110)
        self.assertEqual(bits.extract_bits(0xABCD, 8, 8), 0xAB)
        self.assertEqual(bits.extract_bits(0xFF, 4, 0), 0)
        self.assertEqual(bits.extract_bits(0b101, 1, 10), 0b10)
        self.assertEqual(bits.extract_bits(0b101, 20, 4), 0)

    def test_reverse_bits(self):
        self.assertEqual(bits.reverse_bits(0b0011, 4), 0b1100)
        self.assertEqual(bits.reverse_bits(1, 8), 128)
        self.assertEqual(bits.reverse_bits(0b1011, 4), 0b1101)
        self.assertEqual(bits.reverse_bits(0, 5), 0)
        self.assertEqual(bits.reverse_bits(1, 1), 1)
        self.assertEqual(bits.reverse_bits(0b110, 8), 0b01100000)
        self.assertEqual(bits.reverse_bits(bits.reverse_bits(0xDEAD, 16), 16), 0xDEAD)

    def test_reverse_bits_errors(self):
        with self.assertRaises(ValueError):
            bits.reverse_bits(16, 4)
        with self.assertRaises(ValueError):
            bits.reverse_bits(1, 0)

    def test_lowest_set_bit(self):
        self.assertEqual(bits.lowest_set_bit(12), 4)
        self.assertEqual(bits.lowest_set_bit(1), 1)
        self.assertEqual(bits.lowest_set_bit(0), 0)
        self.assertEqual(bits.lowest_set_bit(2**33 + 2**20), 2**20)

    def test_negative_arguments_raise(self):
        calls = [
            lambda: bits.popcount(-1),
            lambda: bits.next_power_of_two(-1),
            lambda: bits.get_bit(-1, 0),
            lambda: bits.get_bit(1, -1),
            lambda: bits.set_bit(1, -2),
            lambda: bits.clear_bit(-5, 1),
            lambda: bits.toggle_bit(1, -1),
            lambda: bits.extract_bits(1, -1, 1),
            lambda: bits.extract_bits(1, 0, -1),
            lambda: bits.lowest_set_bit(-8),
        ]
        for call in calls:
            with self.assertRaises(ValueError):
                call()


if __name__ == "__main__":
    unittest.main()
