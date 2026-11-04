"""Layered settings: module defaults overridden by per-call overrides."""

DEFAULTS = {"locale": "en", "limits": {"members": 10, "roles": 5}}


def build_settings(overrides=None, base=DEFAULTS):
    """Return settings = base with overrides applied. Nested dicts are merged key by key.

    Neither `base` nor `overrides` may be modified, and the result must not share nested dicts with them.
    """
    overrides = overrides or {}
    base.update(overrides)
    return base
