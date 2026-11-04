from __future__ import annotations

from collections import deque


class JobQueue:
    """FIFO job queue.

    - push(job): appends to the back.
    - pop(): removes and returns the front job; IndexError when empty.
    - drain(handler, limit=None) -> int: calls handler(job) on the front job, then removes
      it, repeatedly, until the queue is empty or `limit` jobs were handled. Jobs pushed by
      a handler while draining go to the back and are handled in the same drain (subject to
      `limit`). Returns the number of jobs handled. A job counts as handled, and is removed,
      only if its handler returned normally. If a handler raises, the exception propagates,
      and the failing job stays at the FRONT of the queue followed by all not yet handled
      jobs in their original order; already handled jobs stay removed.
    - processed: total number of jobs handled successfully by drain over the queue's life.
    - snapshot() -> list: a copy of the pending jobs, front first; changing the returned
      list never affects the queue.
    - len(queue) is the number of pending jobs.
    """

    def __init__(self):
        self._jobs = deque()
        self.processed = 0

    def push(self, job):
        self._jobs.append(job)

    def pop(self):
        if not self._jobs:
            raise IndexError("empty queue")
        return self._jobs.popleft()

    def drain(self, handler, limit=None):
        handled = 0
        while self._jobs and (limit is None or handled < limit):
            handler(self._jobs[0])
            self._jobs.popleft()
            self.processed += 1
            handled += 1
        return handled

    def snapshot(self):
        return list(self._jobs)

    def __len__(self):
        return len(self._jobs)
