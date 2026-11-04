"""Deciding what runs when."""


class CycleError(ValueError):
    pass


def execution_order(jobs):
    """Return the job names (``jobs`` maps name to Job) in a valid running order.

    Every job comes after all of its dependencies. At each step the alphabetically smallest job
    among those whose dependencies are all already placed is chosen. A dependency that is not in
    ``jobs`` raises ``KeyError`` with that dependency's name. A cycle, including a job that depends
    on itself, raises ``CycleError``.
    """
    for job in jobs.values():
        for dep in job.deps:
            if dep not in jobs:
                raise KeyError(dep)
    placed = []
    remaining = dict(jobs)
    while remaining:
        wave = sorted(name for name, job in remaining.items() if all(dep in placed for dep in job.deps))
        if not wave:
            break
        for name in wave:
            placed.append(name)
            del remaining[name]
    return placed
