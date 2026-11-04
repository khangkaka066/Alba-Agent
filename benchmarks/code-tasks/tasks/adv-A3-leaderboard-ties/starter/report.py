"""Ranked report on top of leaderboard.top, using competition ranking (1, 2, 2, 4)."""

from leaderboard import top


def rank_rows(entries, n):
    rows = []
    previous_score = None
    previous_rank = 0
    for position, (name, score) in enumerate(top(entries, n), start=1):
        rank = previous_rank if score == previous_score else position
        rows.append((rank, name, score))
        previous_score, previous_rank = score, rank
    return rows


def render(entries, n):
    return "\n".join(f"{rank}. {name} ({score})" for rank, name, score in rank_rows(entries, n))
