from __future__ import annotations

from typing import Callable, Hashable


class TaskScheduler:
    def __init__(self, clock: Callable[[], float]) -> None:
        raise NotImplementedError

    def schedule(self, task_id: Hashable, run_at: float, priority: int = 0) -> None:
        raise NotImplementedError

    def cancel(self, task_id: Hashable) -> bool:
        raise NotImplementedError

    def reschedule(self, task_id: Hashable, run_at: float, priority: int | None = None) -> None:
        raise NotImplementedError

    def pop_due(self) -> Hashable | None:
        raise NotImplementedError

    def pop_all_due(self) -> list[Hashable]:
        raise NotImplementedError

    def seconds_until_next(self) -> float | None:
        raise NotImplementedError

    def run_at_of(self, task_id: Hashable) -> float:
        raise NotImplementedError

    def __len__(self) -> int:
        raise NotImplementedError

    def __contains__(self, task_id: object) -> bool:
        raise NotImplementedError
