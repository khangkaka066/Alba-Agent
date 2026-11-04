`python -m unittest test_patch` fails: the rendered diff lists changes in the wrong order. `patch.py` renders and applies
diffs, `diff.py` computes them and `lcs.py` holds the table they use. Read the docstrings to see the intended behaviour,
find the root cause and fix it so every diff is produced in the documented order, not only the cases in `test_patch.py`.
Do not modify `test_patch.py`.
