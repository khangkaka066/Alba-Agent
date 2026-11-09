"""Service keys the plugins publish and consume. Plugins import this module, never each other."""

from __future__ import annotations

from nexusgen_bridge.sandbox_team import NexusGenSandboxRunner
from checkpoints.store import CheckpointStore
from nexus_computer_sandbox.interactive import InteractiveComputers
from nexus_computer_sandbox import ComputerSandboxSupervisor
from qdrant_client import AsyncQdrantClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from nexus_kernel import ServiceKey
from nexus_plugins.support.llm_service import LlmService
from nexus_plugins.support.tool_service import ToolRegistryService

DATABASE: ServiceKey[AsyncEngine] = ServiceKey("database")
REDIS: ServiceKey[Redis] = ServiceKey("redis")
QDRANT: ServiceKey[AsyncQdrantClient] = ServiceKey("qdrant")
SANDBOX: ServiceKey[ComputerSandboxSupervisor] = ServiceKey("sandbox")
SANDBOX_RUNNER: ServiceKey[NexusGenSandboxRunner] = ServiceKey("sandbox-runner")
LLM: ServiceKey[LlmService] = ServiceKey("llm")
TOOLS: ServiceKey[ToolRegistryService] = ServiceKey("tools")
CHECKPOINTS: ServiceKey[CheckpointStore] = ServiceKey("checkpoints")

INTERACTIVE_COMPUTERS: ServiceKey[InteractiveComputers] = ServiceKey("interactive-computers")
