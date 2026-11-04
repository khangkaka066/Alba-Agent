"""Ordering of tasks that depend on each other."""

from graph import DiGraph
from toposort import CycleError, postorder  # noqa: F401  (CycleError is re-exported)


def _graph(deps):
    graph = DiGraph()
    for task, needs in deps.items():
        graph.add_node(task)
        for need in needs:
            graph.add_edge(task, need)
    return graph


def build_order(deps):
    """Return a run order for ``deps`` (``{task: [tasks it depends on]}``).

    Every task appears after all of its dependencies. Tasks that only occur as a
    dependency are included too. Among valid orders the one produced by a depth-first
    walk is used (tasks tried in dict order, dependencies in list order). A dependency
    cycle (including a task depending on itself) raises ``CycleError``. Two tasks that
    share a dependency, or a dependency chain that reaches the same task twice, are not
    a cycle.
    """
    return postorder(_graph(deps))


def levels(deps):
    """Group tasks into waves that can run in parallel.

    A task with no dependencies is in wave 0, otherwise its wave is one more than the
    highest wave among its dependencies. Returns a list of lists; tasks inside a wave
    follow ``build_order``.
    """
    order = build_order(deps)
    wave = {}
    for task in order:
        wave[task] = 1 + max((wave[d] for d in deps.get(task, [])), default=-1)
    result = [[] for _ in range(max(wave.values(), default=-1) + 1)]
    for task in order:
        result[wave[task]].append(task)
    return result
