`python -m unittest test_convert` fails: some conversions come out wrong by a large factor. `convert.py` converts values by
chaining known unit relations stored in `registry.py`. Read the docstrings to see the intended behaviour, find the root cause
and fix it so every conversion that the registry can chain is correct, not only the cases in `test_convert.py`.
Do not modify `test_convert.py`.
