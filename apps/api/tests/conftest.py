"""Make monorepo Python packages importable during repository tests."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
for relative in (
    "apps/api", "packages/core-schema/python", "packages/core-schema/templates", "packages/model-gateway",
    "packages/agent-runtime", "packages/learning-transfer", "packages/computer-sandbox",
    "packages/rag-engine", "packages/mcp-hub",
    "packages/agent-skills", "packages/builtin-tools",
):
    sys.path.insert(0, str(ROOT / relative))
