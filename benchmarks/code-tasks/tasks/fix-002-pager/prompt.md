`python -m unittest test_pager` fails. The bug is in `pager.py`. Fix `pager.py` so `paginate` returns the correct
page in general (it is documented as 1-based), not only for the cases in `test_pager.py`. Do not modify `test_pager.py`.
