"""Counting."""

from collections import Counter


def top_n(tokens, n):
    """Return ``[(word, count), ...]`` for the ``n`` most frequent words, most frequent first;
    words with equal counts are ordered alphabetically. ``n <= 0`` gives ``[]``."""
    if n <= 0:
        return []
    return sorted(Counter(tokens).items(), key=lambda item: (-item[1], item[0]))[:n]


def unique_ratio(tokens):
    """Distinct words divided by total words, or 0.0 when there are no words."""
    if not tokens:
        return 0.0
    return len(set(tokens)) / len(tokens)
