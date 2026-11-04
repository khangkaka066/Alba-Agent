import unittest

from textpipe.pipeline import analyse
from textpipe.stats import top_n
from textpipe.tokenizer import tokenize


class TextpipeTests(unittest.TestCase):
    def test_contractions(self):
        self.assertEqual(tokenize("Don't stop, well-known"), ["don't", "stop", "well-known"])

    def test_ties_alphabetical(self):
        self.assertEqual(top_n(["b", "a", "b", "a", "c"], 2), [("a", 2), ("b", 2)])

    def test_one_letter_words_are_kept_by_default(self):
        self.assertEqual(analyse("a b a")["tokens"], 3)


if __name__ == "__main__":
    unittest.main()
