`python -m unittest test_table` fails: a semicolon-separated export produces rows that cannot be read back. `table.py`
writes whole tables and uses the field formatter in `fields.py`. Read the docstrings to see the intended behaviour, find the
root cause and fix it so quoting is correct for every delimiter, not only the cases in `test_table.py`.
Do not modify `test_table.py`.
