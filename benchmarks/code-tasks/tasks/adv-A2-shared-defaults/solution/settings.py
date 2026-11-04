"""Layered settings: module defaults overridden by per-call overrides."""

import copy

DEFAULTS = {"locale": "en", "limits": {"members": 10, "roles": 5}}


def _merge(base, overrides):
    result = copy.deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def build_settings(overrides=None, base=None):
    """Return settings = base with overrides applied. Nested dicts are merged key by key.

    Neither `base` nor `overrides` may be modified, and the result must not share nested dicts with them.
    """
    return _merge(DEFAULTS if base is None else base, overrides or {})
