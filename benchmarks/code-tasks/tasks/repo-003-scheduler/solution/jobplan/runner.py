"""Running jobs."""

from .order import execution_order


def run_all(jobs):
    """Run every job in ``execution_order`` and return ``{name: "ok" | "failed" | "skipped"}``.

    A job whose action raises is "failed" (the exception is swallowed). A job that depends directly
    or indirectly on a job that is "failed" or "skipped" is "skipped" and its action is not called.
    Jobs that do not depend on a failure still run.
    """
    status = {}
    for name in execution_order(jobs):
        job = jobs[name]
        if any(status[dep] != "ok" for dep in job.deps):
            status[name] = "skipped"
            continue
        try:
            job.action()
            status[name] = "ok"
        except Exception:
            status[name] = "failed"
    return status
