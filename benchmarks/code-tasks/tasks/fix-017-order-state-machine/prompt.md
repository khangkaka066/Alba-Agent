`python -m unittest test_order` fails: some order transitions end in the wrong state. The order logic lives in `order.py`
and the generic state machine it uses lives in `workflow.py`; read the docstrings to see the intended behaviour, find
the root cause and fix it so every machine built on `Machine` behaves correctly, not only the order table. Do not modify `test_order.py`.
