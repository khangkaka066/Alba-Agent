import heapq


class CycleError(ValueError):
    """Raised when the dependency graph contains a cycle."""


def _graph(deps: dict[str, list[str]]) -> tuple[dict[str, set[str]], dict[str, list[str]]]:
    prereqs: dict[str, set[str]] = {}
    dependents: dict[str, list[str]] = {}
    for task, requirements in deps.items():
        prereqs.setdefault(task, set())
        for req in requirements:
            prereqs[task].add(req)
            prereqs.setdefault(req, set())
    for task, reqs in prereqs.items():
        for req in reqs:
            dependents.setdefault(req, []).append(task)
    return prereqs, dependents


def topological_order(deps: dict[str, list[str]]) -> list[str]:
    prereqs, dependents = _graph(deps)
    remaining = {task: len(reqs) for task, reqs in prereqs.items()}
    heap = [task for task, n in remaining.items() if n == 0]
    heapq.heapify(heap)
    order: list[str] = []
    while heap:
        task = heapq.heappop(heap)
        order.append(task)
        for nxt in dependents.get(task, []):
            remaining[nxt] -= 1
            if remaining[nxt] == 0:
                heapq.heappush(heap, nxt)
    if len(order) != len(prereqs):
        raise CycleError("dependency cycle detected")
    return order


def execution_levels(deps: dict[str, list[str]]) -> list[list[str]]:
    order = topological_order(deps)
    prereqs, _ = _graph(deps)
    level: dict[str, int] = {}
    for task in order:
        level[task] = 1 + max((level[r] for r in prereqs[task]), default=-1)
    levels: list[list[str]] = [[] for _ in range(max(level.values(), default=-1) + 1)]
    for task in sorted(level):
        levels[level[task]].append(task)
    return levels
