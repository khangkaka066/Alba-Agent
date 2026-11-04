`python -m unittest test_tasks` fails: valid task lists are rejected as cyclic. The public functions are in `tasks.py`; they
use `toposort.py` and `graph.py`. Read the docstrings to see the intended behaviour, find the root cause and fix it so cycle
detection is correct for every graph, not only the cases in `test_tasks.py`. Do not modify `test_tasks.py`.
