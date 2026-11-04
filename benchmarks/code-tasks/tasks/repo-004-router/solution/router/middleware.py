"""Wrapping handlers."""


def wrap(handler, middlewares):
    """Apply ``middlewares`` (each ``f(next_handler) -> handler``) around ``handler``.

    The first middleware in the list is the outermost one: it sees the request first and the
    response last.
    """
    for middleware in reversed(list(middlewares)):
        handler = middleware(handler)
    return handler
