"""Per-model connection settings: how long to wait and how often to retry depends on the model being called."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from fnmatch import fnmatchcase


@dataclass(frozen=True, slots=True)
class ModelProfile:
    timeout_seconds: float = 120.0
    max_retries: int = 3

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_retries < 0:
            raise ValueError("max_retries must be zero or more")


DEFAULT_PROFILE = ModelProfile()

# First matching pattern wins. Reasoning and frontier models think for a long time before the first token, so a short
# timeout turns a slow answer into a failure; small and local models answer fast, so a hung call should fail early.
BUILTIN_PROFILES: tuple[tuple[str, ModelProfile], ...] = (
    ("*reasoner*", ModelProfile(timeout_seconds=300.0, max_retries=2)),
    ("*-r1*", ModelProfile(timeout_seconds=300.0, max_retries=2)),
    ("o1*", ModelProfile(timeout_seconds=300.0, max_retries=2)),
    ("o3*", ModelProfile(timeout_seconds=300.0, max_retries=2)),
    ("*opus*", ModelProfile(timeout_seconds=240.0, max_retries=3)),
    ("*mini*", ModelProfile(timeout_seconds=60.0, max_retries=4)),
    ("*nano*", ModelProfile(timeout_seconds=60.0, max_retries=4)),
    ("*haiku*", ModelProfile(timeout_seconds=60.0, max_retries=4)),
    ("*flash*", ModelProfile(timeout_seconds=60.0, max_retries=4)),
)


def _overrides_from_environment() -> dict[str, ModelProfile]:
    """`NEXUS_MODEL_PROFILES` is a JSON object: {"pattern": {"timeout_seconds": 90, "max_retries": 2}}."""
    raw = os.environ.get("NEXUS_MODEL_PROFILES", "").strip()
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("NEXUS_MODEL_PROFILES must be a JSON object")
    return {
        str(pattern): replace(DEFAULT_PROFILE, **{key: value for key, value in fields.items() if key in ("timeout_seconds", "max_retries")})
        for pattern, fields in data.items()
        if isinstance(fields, dict)
    }


def profile_for(model: str) -> ModelProfile:
    """The profile for a model name; environment overrides come first, then the built-in patterns."""
    name = model.rsplit("/", 1)[-1].lower()
    for pattern, profile in (*_overrides_from_environment().items(), *BUILTIN_PROFILES):
        if fnmatchcase(name, pattern.lower()):
            return profile
    return DEFAULT_PROFILE
