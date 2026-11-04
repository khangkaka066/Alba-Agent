"""Helpers for building tagged records for the catalog importer."""


def build_record(name, tags=None):
    """Return ``{"name": name, "tags": [...]}`` for a catalog entry.

    The record's tags are the given tags (in order) followed by "imported".
    Every call returns a record with its own tag list, and the caller's
    ``tags`` list is never modified.
    """
    own_tags = list(tags) if tags else []
    own_tags.append("imported")
    return {"name": name, "tags": own_tags}


def build_many(names, tags=None):
    """Build one record per name; every record starts from the same given tags."""
    return [build_record(name, tags) for name in names]


def rename(record, new_name):
    """Return a copy of ``record`` with a new name and its own copy of the tags."""
    return {"name": new_name, "tags": list(record["tags"])}


def has_tag(record, tag):
    """True if the record carries ``tag``."""
    return tag in record["tags"]
