"""Leaderboard ordering and ranking."""


def sort_players(players):
    """Order players for display.

    ``players`` is a list of (name, score). Highest score first; players with
    equal scores are ordered alphabetically by name, ignoring case (A before B).
    Returns a new list.
    """
    return sorted(players, key=lambda p: (p[1], p[0].lower()), reverse=True)


def rank_players(players):
    """Return [(rank, name, score)] in display order using competition ranking.

    Players with equal scores share a rank and the next rank skips ahead, so
    scores 10, 10, 7 get ranks 1, 1, 3.
    """
    ordered = sort_players(players)
    ranked = []
    for index, (name, score) in enumerate(ordered):
        if index > 0 and score == ordered[index - 1][1]:
            rank = ranked[-1][0]
        else:
            rank = index + 1
        ranked.append((rank, name, score))
    return ranked


def top_names(players, count):
    """Names of the first ``count`` players in display order."""
    return [name for name, _ in sort_players(players)[:count]]
