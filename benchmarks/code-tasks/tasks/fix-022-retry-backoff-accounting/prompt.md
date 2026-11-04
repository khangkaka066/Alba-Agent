`python -m unittest test_retry` fails: the delays reported by the retry helper do not match the policy. The runner is in
`retry.py`; it uses `backoff.py` and `policy.py`. Read the docstrings to see the intended behaviour, find the root cause and
fix it so the accounting is correct in general, not only for the cases in `test_retry.py`. There may be more than one
defect. Do not modify `test_retry.py`.
