`python -m unittest test_bookings` fails. The bug is in `bookings.py`; the failing assertions may call a function whose
defect lives in a helper it relies on. Fix `bookings.py` so booking logic is correct in general according to the
docstrings, not only for the cases in `test_bookings.py`. Do not modify `test_bookings.py`.
