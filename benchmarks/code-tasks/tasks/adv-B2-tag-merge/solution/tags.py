from __future__ import annotations

import unicodedata


def _key(tag: str) -> str:
    return unicodedata.normalize("NFC", tag).casefold()


def merge_tags(lists: list[list[str]], limit: int | None = None) -> list[str]:
    if limit is not None:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("limit must be an int or None")
        if limit < 0:
            raise ValueError("limit must not be negative")
    counts: dict[str, int] = {}
    spelling: dict[str, str] = {}
    for tags in lists:
        for tag in tags:
            if not isinstance(tag, str):
                raise TypeError(f"tag must be str, got {type(tag).__name__}")
            stripped = tag.strip()
            if not stripped:
                continue
            key = _key(stripped)
            if key not in counts:
                counts[key] = 0
                spelling[key] = stripped
            counts[key] += 1
    # dicts keep first-occurrence order and sorted() is stable, so equal counts keep that order
    ordered = sorted(counts, key=lambda k: -counts[k])
    result = [spelling[k] for k in ordered]
    return result if limit is None else result[:limit]
