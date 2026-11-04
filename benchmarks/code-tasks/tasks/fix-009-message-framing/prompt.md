`python -m unittest test_framing` fails. The bug is in `framing.py` (it shows up with non-ASCII text). Fix `framing.py`
so frames are correct in general according to the module docstring, not only for the cases in `test_framing.py`.
Do not modify `test_framing.py`.
