"""Putting the steps together."""

from .filters import min_length, remove_stopwords
from .stats import top_n, unique_ratio
from .tokenizer import tokenize


def analyse(text, stopwords=(), min_len=1, top=3):
    """Tokenize ``text``, drop tokens shorter than ``min_len``, drop stopwords, and return
    ``{"tokens": <number kept>, "unique_ratio": <rounded to 3 decimals>, "top": top_n(kept, top)}``."""
    tokens = remove_stopwords(min_length(tokenize(text), min_len), stopwords)
    return {"tokens": len(tokens), "unique_ratio": round(unique_ratio(tokens), 3), "top": top_n(tokens, top)}
