"""Splitting text into words."""

import re

_WORD = re.compile(r"[^\W_]+(?:['-][^\W_]+)*")


def tokenize(text):
    """Return the lower-cased words of ``text``, in order.

    A word is a run of letters and digits (any alphabet, so "café" is one word). An apostrophe
    or a hyphen between two letters/digits stays inside the word ("don't", "well-known");
    all other punctuation and whitespace separates words.
    """
    return _WORD.findall(text.lower())
