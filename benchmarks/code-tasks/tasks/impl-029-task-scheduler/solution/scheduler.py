from __future__ import annotations

import heapq
from typing import Callable, Hashable


class TaskScheduler:
    """Two heaps with lazy deletion.

    `_waiting` orders tasks by run time; due tasks are promoted from it into `_ready`,
    which orders them by (priority, run_at, insertion order). Every (re)schedule gets a
    fresh version number; heap entries whose version no longer matches are stale.
    """

    def __init__(self, clock: Callable[[], float]) -> None:
        self._clock = clock
        self._tasks: dict[Hashable, tuple[float, int, int, int]] = {}  # id -> run_at, priority, seq, version
        self._waiting: list[tuple[float, int, int, Hashable]] = []  # run_at, seq, version, id
        self._ready: list[tuple[int, float, int, int, Hashable]] = []  # -priority, run_at, seq, version, id
        self._seq = 0
        self._version = 0

    def _push(self, task_id: Hashable, run_at: float, priority: int, seq: int) -> None:
        self._version += 1
        self._tasks[task_id] = (run_at, priority, seq, self._version)
        heapq.heappush(self._waiting, (run_at, seq, self._version, task_id))

    def _live(self, task_id: Hashable, version: int) -> bool:
        entry = self._tasks.get(task_id)
        return entry is not None and entry[3] == version

    def schedule(self, task_id: Hashable, run_at: float, priority: int = 0) -> None:
        if task_id in self._tasks:
            raise ValueError(f"task {task_id!r} is already pending")
        self._seq += 1
        self._push(task_id, run_at, priority, self._seq)

    def cancel(self, task_id: Hashable) -> bool:
        return self._tasks.pop(task_id, None) is not None

    def reschedule(self, task_id: Hashable, run_at: float, priority: int | None = None) -> None:
        _, old_priority, seq, _ = self._tasks[task_id]
        self._push(task_id, run_at, old_priority if priority is None else priority, seq)

    def _promote(self, now: float) -> None:
        while self._waiting:
            run_at, seq, version, task_id = self._waiting[0]
            if not self._live(task_id, version):
                heapq.heappop(self._waiting)
            elif run_at <= now:
                heapq.heappop(self._waiting)
                priority = self._tasks[task_id][1]
                heapq.heappush(self._ready, (-priority, run_at, seq, version, task_id))
            else:
                break

    def _pop_ready(self) -> Hashable | None:
        while self._ready:
            _, _, _, version, task_id = heapq.heappop(self._ready)
            if self._live(task_id, version):
                del self._tasks[task_id]
                return task_id
        return None

    def pop_due(self) -> Hashable | None:
        self._promote(self._clock())
        return self._pop_ready()

    def pop_all_due(self) -> list[Hashable]:
        self._promote(self._clock())
        result: list[Hashable] = []
        while (task_id := self._pop_ready()) is not None:
            result.append(task_id)
        return result

    def seconds_until_next(self) -> float | None:
        if not self._tasks:
            return None
        now = self._clock()
        self._promote(now)
        while self._ready and not self._live(self._ready[0][4], self._ready[0][3]):
            heapq.heappop(self._ready)
        if self._ready:
            return 0.0
        return max(0.0, self._waiting[0][0] - now)

    def run_at_of(self, task_id: Hashable) -> float:
        return self._tasks[task_id][0]

    def __len__(self) -> int:
        return len(self._tasks)

    def __contains__(self, task_id: object) -> bool:
        return task_id in self._tasks
