`python -m unittest test_reservations` fails: the stock that is reported as available is wrong after releasing or shipping
reservations. The reservation logic is in `reservations.py` and the stock counters are in `inventory.py`. Read the docstrings
to see the intended behaviour, find the root cause and fix it so the accounting stays correct across any sequence of calls,
not only the cases in `test_reservations.py`. There may be more than one defect. Do not modify `test_reservations.py`.
