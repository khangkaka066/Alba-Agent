`python -m unittest test_api` fails: paging through a leaderboard skips some entries. The code is split across `api.py`
(public entry point), `paging.py` and `sorting.py`. Read the docstrings to see the intended behaviour, find the root cause
and fix it so that paging visits every entry exactly once for any page size, not only the cases in `test_api.py`.
Do not modify `test_api.py`.
