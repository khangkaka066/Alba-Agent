`python -m unittest test_money` fails. The bug is in the money/invoice code (`money.py`, `invoice.py`). Money amounts must be
rounded to whole cents with "half away from zero" rounding (0.125 -> 13 cents, -0.125 -> -13 cents), for refunds and
tax as well as for charges. Fix the code so it is correct in general, not only for the cases in `test_money.py`.
Do not modify `test_money.py`.
