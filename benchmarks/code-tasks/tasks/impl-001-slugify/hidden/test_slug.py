import unittest

from slug import slugify


class SlugifyTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(slugify("Hello World"), "hello-world")

    def test_punctuation_runs(self):
        self.assertEqual(slugify("  Hello,   World!!  "), "hello-world")

    def test_accents(self):
        self.assertEqual(slugify("Crème Brûlée à la carte"), "creme-brulee-a-la-carte")

    def test_vietnamese(self):
        self.assertEqual(slugify("Đường Nguyễn Huệ"), "duong-nguyen-hue")

    def test_digits_kept(self):
        self.assertEqual(slugify("Top 10 tips (2024)"), "top-10-tips-2024")

    def test_empty_and_symbols(self):
        self.assertEqual(slugify(""), "")
        self.assertEqual(slugify("!!! ???"), "")

    def test_underscores_are_separators(self):
        self.assertEqual(slugify("snake_case_name"), "snake-case-name")


if __name__ == "__main__":
    unittest.main()
