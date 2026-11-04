"""Layered application configuration."""

import copy

DEFAULTS = {
    "server": {"host": "localhost", "port": 8080},
    "logging": {"level": "INFO", "handlers": ["console"]},
    "debug": False,
}


def merge(base, overrides):
    """Return a new dict: ``base`` updated recursively with ``overrides``.

    Nested dicts are merged key by key; any other value in ``overrides``
    replaces the one in ``base``. Neither input is modified, and the result
    shares no mutable object (dict or list) with either of them.
    """
    result = copy.deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_config(overrides=None):
    """Configuration for one run: DEFAULTS with ``overrides`` applied on top."""
    return merge(DEFAULTS, overrides or {})


def get_path(config, dotted, default=None):
    """Look up 'server.port' style paths; ``default`` if any part is missing."""
    node = config
    for part in dotted.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node
