"""Builds the effective application configuration."""

from merge import deep_merge

DEFAULTS = {
    "db": {"host": "localhost", "port": 5432, "options": {"ssl": False, "pool": 5}},
    "cache": {"ttl": 60},
    "features": ["search"],
}


def apply_env(config, env, prefix="APP_"):
    """Apply environment-style settings to ``config`` in place and return it.

    A variable ``APP_DB__OPTIONS__SSL=true`` sets ``config["db"]["options"]["ssl"]``
    to the string ``"true"``: the prefix is dropped, the rest is lower-cased and ``__``
    separates nesting levels. Missing (or non-dict) intermediate levels are created.
    Variables without the prefix are ignored.
    """
    for name, value in env.items():
        if not name.startswith(prefix):
            continue
        parts = name[len(prefix):].lower().split("__")
        node = config
        for part in parts[:-1]:
            if not isinstance(node.get(part), dict):
                node[part] = {}
            node = node[part]
        node[parts[-1]] = value
    return config


def load_config(overrides=None, env=None):
    """Return DEFAULTS updated by ``overrides`` (a nested dict) and then by ``env``.

    Every call returns an independent configuration: ``DEFAULTS`` and the arguments are
    never modified, and changing a returned config never affects later calls.
    """
    config = deep_merge(DEFAULTS, overrides or {})
    return apply_env(config, env or {})
