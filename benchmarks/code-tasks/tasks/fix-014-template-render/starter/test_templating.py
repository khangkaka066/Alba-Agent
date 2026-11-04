import unittest

from templating import placeholders, render


class TemplatingTests(unittest.TestCase):
    def test_two_on_one_line(self):
        self.assertEqual(render("Hi {{first}} {{last}}!", {"first": "Ada", "last": "Lovelace"}), "Hi Ada Lovelace!")

    def test_names(self):
        self.assertEqual(placeholders("{{a}} and {{b}}"), ["a", "b"])


if __name__ == "__main__":
    unittest.main()
