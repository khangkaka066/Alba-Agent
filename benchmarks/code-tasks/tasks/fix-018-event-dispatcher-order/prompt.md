`python -m unittest test_dispatcher` fails: handlers run in the wrong order. `dispatcher.py` is the public entry point and
`registry.py` stores the subscriptions; read the docstrings to see the intended ordering rules, find the root cause and fix
it so the ordering is correct in general, not only for the cases in `test_dispatcher.py`. Do not modify `test_dispatcher.py`.
