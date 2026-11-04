"""Generic table-driven state machine."""

WILDCARD = "*"


class InvalidTransition(Exception):
    """Raised when an event is not allowed in the current state."""


class Machine:
    """Maps (state, event) pairs to a next state.

    Table keys are ``(state, event)`` tuples. A key whose state is ``"*"`` applies to
    every state. A specific ``(state, event)`` entry always takes priority over the
    ``("*", event)`` entry, and a specific entry whose target is ``None`` forbids the
    event in that state even when a ``"*"`` entry exists.
    """

    def __init__(self, table, initial):
        self.table = dict(table)
        self.initial = initial

    def lookup(self, state, event):
        """Return the next state, or None when ``event`` is not allowed in ``state``."""
        if (state, event) in self.table:
            return self.table[(state, event)]
        return self.table.get((WILDCARD, event))

    def allowed_events(self, state):
        """Sorted list of events that are allowed in ``state``."""
        events = sorted({event for _, event in self.table})
        return [event for event in events if self.lookup(state, event) is not None]
