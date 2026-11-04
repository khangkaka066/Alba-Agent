import unittest

from textpipe.filters import min_length, remove_stopwords
from textpipe.pipeline import analyse
from textpipe.stats import top_n, unique_ratio
from textpipe.tokenizer import tokenize


class TokenizerTests(unittest.TestCase):
    def test_words(self):
        self.assertEqual(tokenize("Hello, World! It's 2024."), ["hello", "world", "it's", "2024"])
        self.assertEqual(tokenize("well-known state-of-the-art"), ["well-known", "state-of-the-art"])
        self.assertEqual(tokenize("Café au lait; naïve"), ["café", "au", "lait", "naïve"])

    def test_edges_of_apostrophes_and_hyphens_separate(self):
        self.assertEqual(tokenize("'quoted' -dash- rock'n'roll"), ["quoted", "dash", "rock'n'roll"])
        self.assertEqual(tokenize("a--b"), ["a", "b"])
        self.assertEqual(tokenize("snake_case"), ["snake", "case"])

    def test_empty(self):
        self.assertEqual(tokenize(""), [])
        self.assertEqual(tokenize(" ... "), [])


class FilterTests(unittest.TestCase):
    def test_stopwords_any_case(self):
        self.assertEqual(remove_stopwords(["the", "cat", "and", "dog"], ["The", "AND"]), ["cat", "dog"])
        self.assertEqual(remove_stopwords(["a"], []), ["a"])

    def test_stopwords_accepts_generator(self):
        self.assertEqual(remove_stopwords(["x", "y"], (w for w in ["X"])), ["y"])

    def test_min_length_inclusive(self):
        self.assertEqual(min_length(["a", "bb", "ccc"], 2), ["bb", "ccc"])
        self.assertEqual(min_length(["a", "bb"], 0), ["a", "bb"])


class StatsTests(unittest.TestCase):
    def test_top_n(self):
        tokens = ["pear", "apple", "pear", "fig", "apple", "kiwi", "fig"]
        self.assertEqual(top_n(tokens, 3), [("apple", 2), ("fig", 2), ("pear", 2)])
        self.assertEqual(top_n(tokens, 10)[-1], ("kiwi", 1))
        self.assertEqual(top_n(tokens, 0), [])
        self.assertEqual(top_n(tokens, -2), [])
        self.assertEqual(top_n([], 3), [])

    def test_unique_ratio(self):
        self.assertEqual(unique_ratio([]), 0.0)
        self.assertEqual(unique_ratio(["a", "a", "b", "b"]), 0.5)


class PipelineTests(unittest.TestCase):
    def test_analyse(self):
        text = "The cat and the dog. The CAT sat; a cat's hat."
        result = analyse(text, stopwords=["THE", "and"], min_len=2, top=2)
        self.assertEqual(result["tokens"], 6)
        self.assertEqual(result["top"], [("cat", 2), ("cat's", 1)])
        self.assertEqual(result["unique_ratio"], round(5 / 6, 3))

    def test_empty_text(self):
        self.assertEqual(analyse(""), {"tokens": 0, "unique_ratio": 0.0, "top": []})

    def test_min_len_default_keeps_single_letters(self):
        self.assertEqual(analyse("a b a", top=1), {"tokens": 3, "unique_ratio": 0.667, "top": [("a", 2)]})


if __name__ == "__main__":
    unittest.main()
