Implement `topological_order` and `execution_levels` in `topo.py`, and use the provided `CycleError`.

Input: `deps: dict[str, list[str]]` maps each task name to the list of tasks it depends on (those must come earlier). A task that appears only inside a dependency list (never as a key) is still a task, with no dependencies of its own. Duplicate entries in a dependency list are harmless. The input must not be modified.

`topological_order(deps) -> list[str]`
- Returns every task exactly once so that each task comes after all of its dependencies.
- Among all valid orders return the lexicographically smallest one (compare task names as plain `str`): at every step pick the alphabetically smallest task whose dependencies are all already placed.
- Empty input -> `[]`.
- If the dependencies contain a cycle (including a task depending on itself), raise `CycleError`.

`execution_levels(deps) -> list[list[str]]`
- Groups tasks into waves. Level 0 holds the tasks with no dependencies; each later level holds the tasks whose dependencies are all in earlier levels and which are not in earlier levels themselves (i.e. a task's level is `1 + max(level of its dependencies)`, or `0` with none). Each level is sorted alphabetically.
- Empty input -> `[]`. A cycle raises `CycleError`.

`CycleError` is a subclass of `ValueError`; it is already defined in the stub, leave it as is.
