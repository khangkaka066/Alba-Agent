import unittest

from money import allocate, format_cents, to_cents


class ToCentsTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(to_cents("19.99"), 1999)
        self.assertEqual(to_cents("5"), 500)
        self.assertEqual(to_cents("0"), 0)
        self.assertEqual(to_cents("0.5"), 50)
        self.assertEqual(to_cents("+3.20"), 320)
        self.assertEqual(to_cents("-3.20"), -320)
        self.assertEqual(to_cents("007.05"), 705)

    def test_rounding_half_away_from_zero(self):
        self.assertEqual(to_cents("0.005"), 1)
        self.assertEqual(to_cents("-0.005"), -1)
        self.assertEqual(to_cents("2.675"), 268)
        self.assertEqual(to_cents("2.674"), 267)
        self.assertEqual(to_cents("-2.675"), -268)
        self.assertEqual(to_cents("1.0049999999"), 100)
        self.assertEqual(to_cents("0.995"), 100)
        self.assertEqual(to_cents("1.234567"), 123)

    def test_tiny_negative_is_zero(self):
        self.assertEqual(to_cents("-0.001"), 0)
        self.assertEqual(to_cents("-0"), 0)

    def test_large_exact(self):
        self.assertEqual(to_cents("12345678901234567.89"), 1234567890123456789)

    def test_invalid(self):
        for text in ["", " 1.00", "1.00 ", "1,000.00", ".5", "5.", "abc", "1e3", "--1", "1.2.3", "$5", "-", "+", "1_0"]:
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    to_cents(text)


class FormatTests(unittest.TestCase):
    def test_values(self):
        self.assertEqual(format_cents(0), "0.00")
        self.assertEqual(format_cents(5), "0.05")
        self.assertEqual(format_cents(100), "1.00")
        self.assertEqual(format_cents(1999), "19.99")
        self.assertEqual(format_cents(123456789), "1234567.89")

    def test_negative(self):
        self.assertEqual(format_cents(-1205), "-12.05")
        self.assertEqual(format_cents(-5), "-0.05")

    def test_round_trip(self):
        for c in (0, 1, 99, 100, 101, -1, -250, 987654321):
            with self.subTest(c=c):
                self.assertEqual(to_cents(format_cents(c)), c)


class AllocateTests(unittest.TestCase):
    def test_even_split_with_leftover_to_lowest_index(self):
        self.assertEqual(allocate(100, [1, 1, 1]), [34, 33, 33])
        self.assertEqual(allocate(2, [1, 1, 1]), [1, 1, 0])
        self.assertEqual(allocate(0, [1, 1]), [0, 0])

    def test_proportional(self):
        self.assertEqual(allocate(1000, [1, 2, 7]), [100, 200, 700])
        self.assertEqual(allocate(10, [3, 1]), [8, 2])  # 7.5 / 2.5 -> tie, lowest index gets the cent

    def test_largest_remainder_not_just_first(self):
        # exact split needs no leftover cents
        self.assertEqual(allocate(10, [5, 3, 2]), [5, 3, 2])
        # 8*[1,1,5]/7 = 1.14, 1.14, 5.71 -> floors 1,1,5 leftover 1 -> largest remainder is index 2
        self.assertEqual(allocate(8, [1, 1, 5]), [1, 1, 6])
        # 5*[1,4,4]/9 = 0.55, 2.22, 2.22 -> floors 0,2,2 leftover 1 -> index 0 has the biggest remainder
        self.assertEqual(allocate(5, [1, 4, 4]), [1, 2, 2])

    def test_two_leftover_cents_to_two_largest_remainders(self):
        # 11*w/10 = 1.1,1.1,1.1,7.7 -> floors 1,1,1,7 (10) leftover 1 -> index 3
        self.assertEqual(allocate(11, [1, 1, 1, 7]), [1, 1, 1, 8])
        # 12*w/10 = 1.2,1.2,1.2,8.4 -> floors 1,1,1,8 (11) leftover 1 -> remainders 2,2,2,4 -> index 3
        self.assertEqual(allocate(12, [1, 1, 1, 7]), [1, 1, 1, 9])
        # 7 split [2,2,3]: 2,2,3 exactly; 8: 2.28,2.28,3.43 -> floors 2,2,3 (7) leftover 1 -> remainders 2,2,3 -> idx 2
        self.assertEqual(allocate(8, [2, 2, 3]), [2, 2, 4])
        # 3 cents among [1,1,1,1]: remainders all 3 -> first three get one
        self.assertEqual(allocate(3, [1, 1, 1, 1]), [1, 1, 1, 0])

    def test_zero_weights_get_nothing(self):
        self.assertEqual(allocate(5, [0, 1, 0, 1]), [0, 3, 0, 2])
        self.assertEqual(allocate(7, [0, 5]), [0, 7])

    def test_sum_always_exact(self):
        for total in range(0, 60):
            for weights in ([1], [1, 2], [3, 3, 3], [5, 0, 7, 11], [1, 1, 1, 1, 1, 1, 1]):
                with self.subTest(total=total, weights=weights):
                    shares = allocate(total, weights)
                    self.assertEqual(sum(shares), total)
                    self.assertEqual(len(shares), len(weights))

    def test_errors(self):
        for args in [(-1, [1]), (10, []), (10, [0, 0]), (10, [1, -1])]:
            with self.subTest(args=args):
                with self.assertRaises(ValueError):
                    allocate(*args)


if __name__ == "__main__":
    unittest.main()
