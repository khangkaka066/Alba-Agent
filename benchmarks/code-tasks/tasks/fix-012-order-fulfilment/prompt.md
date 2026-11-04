`python -m unittest test_fulfilment` fails. The bug is in `fulfilment.py`; one of the failing assertions goes through a
helper, so look at what that helper is supposed to return. Fix `fulfilment.py` so it follows the docstrings in general,
not only for the cases in `test_fulfilment.py`. Do not modify `test_fulfilment.py`.
