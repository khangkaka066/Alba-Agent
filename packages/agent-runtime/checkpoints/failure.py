"""A readable, safe account of why a run failed: where it stopped, what kind of error, and a short trace."""

from __future__ import annotations

import re
import traceback
from datetime import datetime, timezone
from pathlib import PurePosixPath
from collections.abc import Sequence
from typing import Any

_SECRETS = (
    (re.compile(r"\b(?:sk|nx-sk|ghp|gho|xox[abp])-?[A-Za-z0-9_\-]{12,}"), "[secret]"),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-]{8,}"), "Bearer [secret]"),
    (re.compile(r"(?i)\b(api[_-]?key|token|secret|password|authorization)\b(\s*[=:]\s*)\S+"), r"\1\2[secret]"),
    (re.compile(r"\b[a-z][a-z0-9+.\-]*://[^\s/@]+:[^\s/@]+@\S+"), "[connection string]"),
    (re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"), "[token]"),
)
_PATH = re.compile(r"(?:/workspace|/home/[^/\s]+|/Users/[^/\s]+|/usr/local/lib/python[\d.]+/site-packages|/var/lib/nexus)(/\S*)?")
MESSAGE_LIMIT = 600
TRACE_FRAMES = 4


def redact(text: str) -> str:
    """Remove credentials and server paths from text that is shown to the person who started the run."""
    for pattern, replacement in _SECRETS:
        text = pattern.sub(replacement, text)
    return _PATH.sub(lambda match: "…/" + PurePosixPath(match.group(0)).name if match.group(1) else "[path]", text)


def _trace(error: BaseException) -> str:
    frames = traceback.extract_tb(error.__traceback__)[-TRACE_FRAMES:]
    lines = [f"{PurePosixPath(frame.filename).name}:{frame.lineno} in {frame.name}" for frame in frames]
    return redact(" → ".join(lines))[:MESSAGE_LIMIT]


def describe_failure(error: BaseException, *, node_id: str | None = None, node_label: str | None = None, agent: str | None = None) -> dict[str, Any]:
    """The structured failure stored on the run. The agent is recorded only when the failing code path knew it."""
    return {
        "failed_node_id": node_id, "failed_node_label": node_label, "failed_agent_name": agent,
        "error_type": type(error).__name__,
        "error_message": redact(str(error) or type(error).__name__)[:MESSAGE_LIMIT],
        "traceback_summary": _trace(error),
        "occurred_at": datetime.now(timezone.utc).isoformat(),
    }


_MISSING_MODEL = re.compile(r"model[_ ]not[_ ]found|unknown model|no such model|(?:model\b.*(?:not found|does not exist))|(?:(?:not found|does not exist)\b.*\bmodel)", re.IGNORECASE)


def is_model_not_found(error: BaseException) -> bool:
    """True when a provider says the requested model does not exist for this account (not a missing file or run)."""
    return bool(_MISSING_MODEL.search(f"{type(error).__name__} {error}"))


def with_model_suggestions(failure: dict[str, Any], suggestions: Sequence[str]) -> dict[str, Any]:
    """A copy of the stored failure that names models the user can switch to; unchanged when there are none."""
    if not suggestions:
        return failure
    hint = " Try a model you set as default: " + ", ".join(suggestions[:3]) + "."
    return {**failure, "error_message": str(failure["error_message"]) + hint, "suggested_models": list(suggestions[:3])}
