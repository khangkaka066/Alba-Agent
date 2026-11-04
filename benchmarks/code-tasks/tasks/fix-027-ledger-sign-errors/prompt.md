`python -m unittest test_report` fails: balances in the account statement are wrong. The statement is built in `report.py`
from an `Account` (`account.py`) that records entries defined in `ledger.py`. Read the docstrings to see the intended
behaviour, find the root cause and fix it so every balance is correct, not only the cases in `test_report.py`.
Do not modify `test_report.py`.
