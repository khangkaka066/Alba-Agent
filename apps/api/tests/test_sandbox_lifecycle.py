"""Node leases preserve task sessions; explicit retirement and orphan sweeps reclaim computers."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from nexusgen_bridge.sandbox_team import NexusGenSandboxRunner
from nexus_computer_sandbox import ComputerHandle, ComputerSandboxSupervisor, DockerSandboxProvider
from pathlib import Path


class RecordingSupervisor(ComputerSandboxSupervisor):
    """A supervisor that records acquire and release instead of touching a database or Docker."""

    def __init__(self) -> None:  # noqa: D107 - the real constructor needs an engine
        self.events: list[str] = []
        self._run_users: dict[UUID, int] = {}

    async def release_run(self, tenant_id: UUID, workspace_id: UUID, run_id: UUID) -> None:
        self.events.append("release")
        await super().release_run(tenant_id, workspace_id, run_id)

    async def retire_run(self, tenant_id: UUID, workspace_id: UUID, run_id: UUID, host_backed_only: bool = False) -> None:
        self.events.append("retire")


def runner_with(supervisor: Any, limit: str, monkeypatch: pytest.MonkeyPatch) -> NexusGenSandboxRunner:
    monkeypatch.setenv("NEXUS_SANDBOX_MAX_CONCURRENT", limit)
    return NexusGenSandboxRunner(supervisor, lambda _model: None)  # type: ignore[arg-type,return-value]


def emitter() -> Any:
    return SimpleNamespace(tenant_id=uuid4(), workspace_id=uuid4(), run_id=uuid4())


def test_container_is_released_after_a_node_even_when_it_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    supervisor = RecordingSupervisor()
    runner = runner_with(supervisor, "4", monkeypatch)

    async def failing(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("model unavailable")

    runner._run_node = failing  # type: ignore[assignment]
    with pytest.raises(RuntimeError, match="model unavailable"):
        asyncio.run(runner.run("task", SimpleNamespace(), emitter()))  # type: ignore[arg-type]
    assert supervisor.events == ["release"]
    assert supervisor._run_users == {}


def test_overlapping_nodes_of_one_run_keep_the_container_until_the_last_finishes(monkeypatch: pytest.MonkeyPatch) -> None:
    supervisor = RecordingSupervisor()
    runner = runner_with(supervisor, "4", monkeypatch)
    shared = emitter()
    gate = asyncio.Event()
    still_held: list[int] = []

    async def node(*_args: object, **_kwargs: object) -> str:
        if not gate.is_set():
            still_held.append(supervisor._run_users[shared.run_id])
            await gate.wait()
        return "ok"

    runner._run_node = node  # type: ignore[assignment]

    async def scenario() -> None:
        first = asyncio.create_task(runner.run("a", SimpleNamespace(), shared))  # type: ignore[arg-type]
        await asyncio.sleep(0)
        second = asyncio.create_task(runner.run("b", SimpleNamespace(), shared))  # type: ignore[arg-type]
        await asyncio.sleep(0.01)
        gate.set()
        await asyncio.gather(first, second)

    asyncio.run(scenario())
    assert supervisor.events.count("release") == 2
    assert supervisor.events.count("retire") == 0  # later nodes and live previews reuse the same computer


def test_only_the_configured_number_of_nodes_run_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    supervisor = RecordingSupervisor()
    runner = runner_with(supervisor, "2", monkeypatch)
    running = peak = 0

    async def node(*_args: object, **_kwargs: object) -> str:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.02)
        running -= 1
        return "ok"

    runner._run_node = node  # type: ignore[assignment]

    async def scenario() -> None:
        await asyncio.gather(*(runner.run("t", SimpleNamespace(), emitter()) for _ in range(6)))  # type: ignore[arg-type]

    asyncio.run(scenario())
    assert peak == 2


def test_run_owned_containers_are_listed_with_their_age_and_others_are_ignored(tmp_path: Path) -> None:
    provider = DockerSandboxProvider(tmp_path)
    tenant, workspace, run = uuid4(), uuid4(), uuid4()
    created = (datetime.now(timezone.utc) - timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%S.%f") + "123Z"

    async def fake(*arguments: str) -> tuple[int, str, str]:
        if arguments[0] == "ps":
            return 0, "aaa\nbbb\n", ""
        return 0, f"/nexus-computer-1|{created}|{tenant}|{workspace}|{run}\n/odd||||\n", ""

    provider._docker = fake  # type: ignore[method-assign]
    found = asyncio.run(provider.run_owned_containers())
    assert len(found) == 1
    name, found_tenant, found_workspace, found_run, age = found[0]
    assert (name, found_tenant, found_workspace, found_run) == ("nexus-computer-1", tenant, workspace, run)
    assert 5 * 3600 - 60 < age < 5 * 3600 + 60


def test_provisioning_retries_a_busy_daemon_then_gives_up(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []

    async def no_wait(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(asyncio, "sleep", no_wait)

    class Flaky:
        name = "docker"

        def __init__(self, failures: int) -> None:
            self.failures = failures
            self.calls = 0

        async def create(self, handle: ComputerHandle) -> str:
            self.calls += 1
            if self.calls <= self.failures:
                raise RuntimeError("daemon busy")
            return "computer-1"

    handle: Any = SimpleNamespace()
    recovering = Flaky(2)
    assert asyncio.run(ComputerSandboxSupervisor._provision(recovering, handle)) == "computer-1"  # type: ignore[arg-type]
    assert recovering.calls == 3 and sleeps == [1.5, 3.0]
    hopeless = Flaky(9)
    with pytest.raises(RuntimeError, match="daemon busy"):
        asyncio.run(ComputerSandboxSupervisor._provision(hopeless, handle))  # type: ignore[arg-type]
    assert hopeless.calls == 3
