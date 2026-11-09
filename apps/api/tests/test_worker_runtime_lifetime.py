"""A task returning must not cancel the loop that owns its terminal and preview."""
from __future__ import annotations

import asyncio
import threading
from typing import Any, cast

import pytest

from app.services import AppServices
from app.workers import jobs


def test_worker_keeps_one_live_loop_and_services_between_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    loops: list[int] = []
    progressed = threading.Event()

    class Services:
        async def shutdown(self) -> None:
            events.append("shutdown")

    services = Services()

    async def factory() -> AppServices:
        events.append("boot")
        return cast(AppServices, services)

    class Executor:
        def __init__(self, active: AppServices) -> None:
            assert active is cast(Any, services)

        async def scan_routines(self) -> dict[str, int]:
            loops.append(id(asyncio.get_running_loop()))
            if len(loops) == 1:
                async def background() -> None:
                    await asyncio.sleep(.03)
                    progressed.set()
                asyncio.create_task(background())
            return {"tasks": len(loops)}

    monkeypatch.setattr(jobs, "WorkerExecutor", Executor)
    runtime = jobs._WorkerRuntime(factory)
    try:
        assert runtime.run("scan_routines", ()) == {"tasks": 1}
        assert progressed.wait(timeout=2), "Background work must progress while no Celery task is executing"
        assert runtime.run("scan_routines", ()) == {"tasks": 2}
        assert loops[0] == loops[1]
        assert events == ["boot"]
    finally:
        runtime.close()
    runtime.close()
    assert events == ["boot", "shutdown"]
    assert not runtime.thread.is_alive()
