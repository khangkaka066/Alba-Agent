Our document editor keeps a history of document states. Implement the `History` class in `history.py`. States are arbitrary JSON-like values (lists, dicts, strings, numbers, nested).

- `History(initial, limit=None)`: starts with `initial` as the current state and nothing to undo or redo. `limit`, if given (an int >= 1), is the maximum number of undo steps kept; `limit=None` means unlimited. A `limit` below 1 raises `ValueError`.
- `current` (property): the current state.
- `commit(state) -> bool`: makes `state` the new current state. If `state` is equal (`==`) to the current state, nothing at all happens (history and redo steps are untouched) and it returns `False`. Otherwise the previous state becomes undoable, every pending redo step is discarded, and it returns `True`. If the number of undo steps then exceeds `limit`, the oldest states are forgotten so exactly `limit` undo steps remain.
- `undo() -> object`: moves to the previous state and returns it; raises `IndexError` if there is nothing to undo (state unchanged).
- `redo() -> object`: moves forward again and returns that state; raises `IndexError` if there is nothing to redo.
- `can_undo`, `can_redo` (properties): booleans. `undo_steps`, `redo_steps` (properties): how many times `undo()` / `redo()` can currently be called in a row.

States stored in the history must be isolated from the caller: mutating an object after passing it to `History` (or to `commit`), or mutating an object returned from `current`, `undo()` or `redo()`, must never change anything inside the history.
