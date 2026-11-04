"""Token filters."""


def remove_stopwords(tokens, stopwords):
    """Drop every token that is a stopword. Stopwords are compared case-insensitively:
    they may be given in any case, tokens are already lower-case."""
    stop = {word.lower() for word in stopwords}
    return [token for token in tokens if token not in stop]


def min_length(tokens, n):
    """Keep the tokens that have at least ``n`` characters."""
    return [token for token in tokens if len(token) >= n]
