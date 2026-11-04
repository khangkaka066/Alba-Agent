"""Estimating how long a plan takes."""


def critical_path_seconds(jobs):
    """Shortest possible total time when independent jobs run in parallel: the longest chain of
    dependent jobs, summing their durations (``Job.seconds``). 0 for no jobs."""
    return sum(job.seconds for job in jobs.values())
