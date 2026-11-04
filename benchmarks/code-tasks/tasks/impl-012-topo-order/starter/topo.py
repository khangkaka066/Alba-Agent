class CycleError(ValueError):
    """Raised when the dependency graph contains a cycle."""


def topological_order(deps: dict[str, list[str]]) -> list[str]:
    raise NotImplementedError


def execution_levels(deps: dict[str, list[str]]) -> list[list[str]]:
    raise NotImplementedError
