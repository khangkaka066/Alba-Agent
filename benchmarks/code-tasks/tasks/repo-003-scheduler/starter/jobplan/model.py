"""Job description."""

from .timeparse import parse_duration


class Job:
    """A named unit of work. ``duration`` is an int number of seconds or a string for ``parse_duration``;
    ``deps`` are the names of the jobs that must finish first; ``action`` is a zero-argument callable."""

    def __init__(self, name, duration, deps=(), action=None):
        self.name = name
        self.seconds = duration if isinstance(duration, int) else parse_duration(duration)
        self.deps = tuple(deps)
        self.action = action or (lambda: None)
