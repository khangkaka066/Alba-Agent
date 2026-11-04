`python -m unittest test_loader` fails: a configuration loaded earlier seems to affect the one loaded later. The loader is in
`loader.py` and it relies on `merge.py`; read the docstrings in both to see the intended behaviour, find the root cause and
fix it so the behaviour is correct in general, not only for the cases in `test_loader.py`. There may be more than one defect.
Do not modify `test_loader.py`.
