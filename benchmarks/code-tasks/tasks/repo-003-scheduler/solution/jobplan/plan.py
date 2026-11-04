"""Estimating how long a plan takes."""

from .order import execution_order


def critical_path_seconds(jobs):
    """Shortest possible total time when independent jobs run in parallel: the longest chain of
    dependent jobs, summing their durations (``Job.seconds``). 0 for no jobs."""
    finish = {}
    for name in execution_order(jobs):
        job = jobs[name]
        finish[name] = job.seconds + max((finish[dep] for dep in job.deps), default=0)
    return max(finish.values(), default=0)
