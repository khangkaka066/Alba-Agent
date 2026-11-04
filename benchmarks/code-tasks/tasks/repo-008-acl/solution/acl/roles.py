"""Roles and inheritance."""


class Role:
    """A named set of permission strings that also inherits the permissions of its ``parents`` (role names)."""

    def __init__(self, name, perms=(), parents=()):
        self.name = name
        self.perms = set(perms)
        self.parents = tuple(parents)


def effective_perms(roles, name):
    """The permissions of role ``name`` together with those of all its ancestors (through ``parents``, transitively), as a set.

    ``roles`` maps role names to Role objects. An unknown role, whether ``name`` itself or one of the parents, is a
    KeyError carrying that role's name. A cycle in the parent graph reachable from ``name`` is a ValueError.
    A role reachable through two different parents (a diamond) is not a cycle.
    """
    result = set()
    finished = set()

    def visit(current, path):
        if current in path:
            raise ValueError("role cycle")
        role = roles[current]
        if current in finished:
            return
        path = path + (current,)
        result.update(role.perms)
        for parent in role.parents:
            visit(parent, path)
        finished.add(current)

    visit(name, ())
    return result
