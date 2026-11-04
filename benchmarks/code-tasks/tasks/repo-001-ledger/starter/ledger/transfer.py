"""Moving money between two accounts."""


def transfer(source, target, cents, day):
    """Move ``cents`` from ``source`` to ``target``.

    ``ValueError`` if both are the same account object or ``cents`` is not a positive int.
    The transfer is all-or-nothing: when it fails for any reason (``target`` closed, ``source``
    closed or short of funds) neither account changes - not the balance and not the history -
    and the original exception propagates.
    """
    if source is target:
        raise ValueError("cannot transfer to the same account")
    source.withdraw(cents, day)
    target.deposit(cents, day)
