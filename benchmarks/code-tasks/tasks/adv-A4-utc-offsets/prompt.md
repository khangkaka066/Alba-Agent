`python -m unittest test_tz` fails. The bug is in the timestamp code (`tz.py`, `window.py`). Timestamps may carry any
UTC offset (including half-hour offsets); timestamps with no offset are treated as UTC. Fix the code so it is
correct in general, not only for the cases in `test_tz.py`. Do not modify `test_tz.py`.
