"""Order lifecycle built on the generic state machine."""

from workflow import InvalidTransition, Machine

ORDER_MACHINE = Machine(
    {
        ("new", "pay"): "paid",
        ("paid", "ship"): "shipped",
        ("shipped", "deliver"): "delivered",
        ("refunding", "refund"): "cancelled",
        # Any state can be cancelled directly ...
        ("*", "cancel"): "cancelled",
        # ... except: a paid order must be refunded first, and orders that already
        # shipped, were delivered or are cancelled cannot be cancelled.
        ("paid", "cancel"): "refunding",
        ("shipped", "cancel"): None,
        ("delivered", "cancel"): None,
        ("cancelled", "cancel"): None,
    },
    initial="new",
)


class Order:
    """An order that moves through ORDER_MACHINE one event at a time."""

    def __init__(self, order_id, machine=ORDER_MACHINE):
        self.order_id = order_id
        self.machine = machine
        self.state = machine.initial
        self.history = []

    def can(self, event):
        return self.machine.lookup(self.state, event) is not None

    def fire(self, event):
        """Apply ``event`` and return the new state.

        An event that is not allowed raises InvalidTransition and leaves both the state
        and the history untouched. Each successful event appends
        ``(old_state, event, new_state)`` to ``history``.
        """
        target = self.machine.lookup(self.state, event)
        if target is None:
            raise InvalidTransition(f"{event!r} is not allowed in state {self.state!r}")
        self.history.append((self.state, event, target))
        self.state = target
        return target
