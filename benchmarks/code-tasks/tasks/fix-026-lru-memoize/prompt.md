`python -m unittest test_memo` fails: the memoizing decorator evicts or recomputes values it should have kept. The decorator is
in `memo.py` and the cache it builds on is in `lru.py`. Read the docstrings to see the intended behaviour, find the root
cause and fix it so caching and eviction are correct in general, not only for the cases in `test_memo.py`. There may be more
than one defect. Do not modify `test_memo.py`.
