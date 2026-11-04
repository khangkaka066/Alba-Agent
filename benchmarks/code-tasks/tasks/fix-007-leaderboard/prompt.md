`python -m unittest test_leaderboard` fails. The bug is in `leaderboard.py`; check the function the failing assertions
depend on, not only the one they call. Fix `leaderboard.py` so ordering and ranking follow the docstrings in general,
not only for the cases in `test_leaderboard.py`. Do not modify `test_leaderboard.py`.
