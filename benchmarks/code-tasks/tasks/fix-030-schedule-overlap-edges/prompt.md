`python -m unittest test_bookings` fails: meetings that follow each other directly are reported as conflicting. The scheduling
logic is in `bookings.py` and relies on `intervals.py`. Read the docstrings to see the intended behaviour, find the root cause
and fix it so conflicts and free slots are correct in general, not only for the cases in `test_bookings.py`.
Do not modify `test_bookings.py`.
