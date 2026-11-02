"""Which agent of a crew was working, and which one raised the error.

CrewAI reports a failure for the crew as a whole. Wrapping each agent's `execute_task` on the built instances (nothing global,
so crews running side by side in one process never mix) lets the run record name the agent instead of only its department.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any


class AgentTracker:
    def __init__(self) -> None:
        self.current: str | None = None  # the agent that started last
        self.failed: str | None = None  # the agent whose task raised

    @property
    def culprit(self) -> str | None:
        return self.failed or self.current


def _role(agent: Any) -> str:
    return str(getattr(agent, "role", "") or "agent").strip()[:200]


def track_agents(crew: Any) -> AgentTracker:
    """Wrap every agent of `crew` (the manager of a hierarchical crew included) so the tracker follows the work."""
    tracker = AgentTracker()
    agents = list(getattr(crew, "agents", None) or ())
    manager = getattr(crew, "manager_agent", None)
    if manager is not None:
        agents.append(manager)

    def wrap_sync(original: Callable[..., Any], role: str) -> Callable[..., Any]:
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            tracker.current = role
            try:
                return original(*args, **kwargs)
            except Exception:
                tracker.failed = role
                raise

        return wrapped

    def wrap_async(original: Callable[..., Awaitable[Any]], role: str) -> Callable[..., Awaitable[Any]]:
        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            tracker.current = role
            try:
                return await original(*args, **kwargs)
            except Exception:
                tracker.failed = role
                raise

        return wrapped

    for agent in agents:
        role = _role(agent)
        for name, wrapper in (("execute_task", wrap_sync), ("aexecute_task", wrap_async)):
            original = getattr(agent, name, None)
            if callable(original):
                agent.__dict__[name] = wrapper(original, role)  # an instance entry shadows the class method; pydantic fields are untouched
    return tracker
