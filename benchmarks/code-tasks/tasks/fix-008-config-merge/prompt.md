`python -m unittest test_config` fails. The bug is in `config.py`: `load_config` hands back data that is not independent
of the module defaults or of its arguments, as its docstrings promise. Fix `config.py` so this holds in general, not only
for the cases in `test_config.py`. Do not modify `test_config.py`.
