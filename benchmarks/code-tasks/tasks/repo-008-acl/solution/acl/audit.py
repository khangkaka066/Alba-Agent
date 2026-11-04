"""Authorising users and keeping a log."""

from .policy import can
from .roles import effective_perms


def authorize(roles, role_names, action, log=None):
    """Whether a user holding the roles named in ``role_names`` may do ``action``.

    The user's permissions are the union of the effective permissions of every named role (an unknown role is a
    KeyError). With no roles nothing is allowed. When ``log`` (a list) is given, one entry is appended for every call:
    ``{"action": action, "allowed": <bool>, "roles": <sorted list of the role names>}``. The entry is a snapshot, so
    later changes to ``role_names`` must not change it.
    """
    perms = set()
    for name in role_names:
        perms |= effective_perms(roles, name)
    allowed = can(perms, action)
    if log is not None:
        log.append({"action": action, "allowed": allowed, "roles": sorted(role_names)})
    return allowed
