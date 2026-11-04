"""Deciding what runs when."""

import heapq


class CycleError(ValueError):
    pass


def execution_order(jobs):
    """Return the job names (``jobs`` maps name to Job) in a valid running order.

    Every job comes after all of its dependencies. At each step the alphabetically smallest job
    among those whose dependencies are all already placed is chosen. A dependency that is not in
    ``jobs`` raises ``KeyError`` with that dependency's name. A cycle, including a job that depends
    on itself, raises ``CycleError``.
    """
    waiting = {}
    dependents = {name: [] for name in jobs}
    for name, job in jobs.items():
        for dep in job.deps:
            if dep not in jobs:
                raise KeyError(dep)
        waiting[name] = len(set(job.deps))
        for dep in set(job.deps):
            dependents[dep].append(name)
    ready = [name for name, count in waiting.items() if count == 0]
    heapq.heapify(ready)
    placed = []
    while ready:
        name = heapq.heappop(ready)
        placed.append(name)
        for child in dependents[name]:
            waiting[child] -= 1
            if waiting[child] == 0:
                heapq.heappush(ready, child)
    if len(placed) != len(jobs):
        raise CycleError("dependency cycle")
    return placed
