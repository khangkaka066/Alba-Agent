"""Deep merge of nested configuration dictionaries."""


def deep_merge(base, override):
    """Return a new dict made of ``base`` updated with ``override``.

    * Two dicts under the same key are merged recursively; any other override value
      replaces the base value.
    * An override value of ``None`` removes the key from the result (a ``None`` for a key
      that is absent from ``base`` simply leaves it absent). This also applies inside
      nested override dicts.
    * Neither input is modified, and the result shares no mutable containers (dicts or
      lists) with either input, so the caller may mutate the result freely.
    """
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result
