"""Ensure production tools expose usable CrewAI arguments and real artifacts."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, cast

from nexus_builtin_tools.registry import BuiltinToolRegistry, ToolContext


def test_crewai_media_and_report_tools_accept_flat_arguments(tmp_path: Path) -> None:
    async def media(kind: str, payload: dict[str, Any]) -> dict[str, str]:
        return {"kind": kind, "artifact": payload["filename"] + ".mp4"}

    registry = BuiltinToolRegistry(ToolContext("tenant", "workspace", "run", tmp_path, media=media))
    tools = {tool.tool_id: tool for tool in registry.crewai_tools()}
    video = tools["media_generation"]
    report = tools["report_exporter"]
    assert {"kind", "prompt", "filename"}.issubset(video.args_schema.model_fields)
    assert {"content", "filename"}.issubset(report.args_schema.model_fields)

    video_result = json.loads(asyncio.run(video._arun(kind="video", prompt="Museum camera", filename="museum")))
    report_result = json.loads(asyncio.run(report._arun(content="Museum camera script", filename="museum_script")))

    assert video_result == {"kind": "video", "artifact": "museum.mp4"}
    assert report_result["artifact"] == "museum_script.md"
    assert (tmp_path / "museum_script.md").read_text() == "Museum camera script"

    async def crewai_thread_call() -> dict[str, str]:
        bound = BuiltinToolRegistry(ToolContext("tenant", "workspace", "run", tmp_path, media=media))
        bound_video = next(tool for tool in bound.crewai_tools() if tool.tool_id == "media_generation")
        return cast(dict[str, str], json.loads(await asyncio.to_thread(
            bound_video.run, kind="video", prompt="Museum camera", filename="museum_thread"
        )))

    assert asyncio.run(crewai_thread_call())["artifact"] == "museum_thread.mp4"
