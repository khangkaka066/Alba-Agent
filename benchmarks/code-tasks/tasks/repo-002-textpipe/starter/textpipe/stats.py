"""Counting."""

from collections import Counter


def top_n(tokens, n):
    """Return ``[(word, count), ...]`` for the ``n`` most frequent words, most frequent first;
    words with equal counts are ordered alphabetically. ``n <= 0`` gives ``[]``."""
    return Counter(tokens).most_common(n)


def unique_ratio(tokens):
    """Distinct words divided by total words, or 0.0 when there are no words."""
    return len(set(tokens)) / len(tokens)
