"""Accounts that record every movement."""


class InsufficientFunds(Exception):
    pass


class ClosedAccount(Exception):
    pass


class Account:
    def __init__(self, name, balance=0):
        self.name = name
        self.balance = balance
        self.closed = False
        self.history = []

    def deposit(self, cents, day):
        """Add ``cents`` and record ("deposit", cents, day).

        Checks, in this order: ``cents`` must be a positive int (else ValueError), then the
        account must be open (else ClosedAccount).
        """
        if not isinstance(cents, int) or cents <= 0:
            raise ValueError("amount must be a positive integer")
        if self.closed:
            raise ClosedAccount(self.name)
        self.balance += cents
        self.history.append(("deposit", cents, day))

    def withdraw(self, cents, day):
        """Remove ``cents`` and record ("withdraw", cents, day).

        Checks, in this order: ``cents`` must be a positive int (else ValueError), the account
        must be open (else ClosedAccount), and the balance must cover it (else InsufficientFunds).
        Withdrawing exactly the balance is allowed.
        """
        if not isinstance(cents, int) or cents <= 0:
            raise ValueError("amount must be a positive integer")
        if self.closed:
            raise ClosedAccount(self.name)
        if cents > self.balance:
            raise InsufficientFunds(self.name)
        self.balance -= cents
        self.history.append(("withdraw", cents, day))

    def close(self):
        self.closed = True
