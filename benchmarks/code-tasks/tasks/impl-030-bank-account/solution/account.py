from __future__ import annotations

OVERDRAFT_FEE = 500


class AccountError(Exception):
    pass


class AccountStateError(AccountError):
    pass


class InsufficientFundsError(AccountError):
    pass


class DailyLimitError(AccountError):
    pass


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


class Account:
    def __init__(
        self,
        owner: str,
        overdraft_limit: int = 0,
        daily_withdrawal_limit: int | None = None,
    ) -> None:
        if not _is_int(overdraft_limit) or overdraft_limit < 0:
            raise ValueError("overdraft_limit must be an int >= 0")
        if daily_withdrawal_limit is not None and (not _is_int(daily_withdrawal_limit) or daily_withdrawal_limit < 1):
            raise ValueError("daily_withdrawal_limit must be None or an int >= 1")
        self._owner = owner
        self._overdraft_limit = overdraft_limit
        self._daily_limit = daily_withdrawal_limit
        self._balance = 0
        self._state = "open"
        self._history: list[tuple[str, int, int]] = []
        self._withdrawn: dict[int, int] = {}

    @property
    def owner(self) -> str:
        return self._owner

    @property
    def balance(self) -> int:
        return self._balance

    @property
    def state(self) -> str:
        return self._state

    @property
    def history(self) -> list[tuple[str, int, int]]:
        return list(self._history)

    def withdrawn_on(self, day: int) -> int:
        return self._withdrawn.get(day, 0)

    @staticmethod
    def _check_amount(amount: int) -> None:
        if not _is_int(amount):
            raise TypeError("amount must be an int")
        if amount <= 0:
            raise ValueError("amount must be positive")

    def deposit(self, amount: int) -> None:
        self._check_amount(amount)
        if self._state == "closed":
            raise AccountStateError("account is closed")
        self._balance += amount
        self._history.append(("deposit", amount, self._balance))

    def withdraw(self, amount: int, day: int) -> None:
        self._check_amount(amount)
        if not _is_int(day):
            raise TypeError("day must be an int")
        if self._state != "open":
            raise AccountStateError(f"account is {self._state}")
        if self._daily_limit is not None and self._withdrawn.get(day, 0) + amount > self._daily_limit:
            raise DailyLimitError("daily withdrawal limit exceeded")
        after = self._balance - amount
        fee = OVERDRAFT_FEE if self._balance >= 0 and after < 0 else 0
        if after - fee < -self._overdraft_limit:
            raise InsufficientFundsError("insufficient funds")
        self._withdrawn[day] = self._withdrawn.get(day, 0) + amount
        self._history.append(("withdraw", amount, after))
        self._balance = after
        if fee:
            self._balance -= fee
            self._history.append(("fee", fee, self._balance))

    def freeze(self) -> None:
        if self._state != "open":
            raise AccountStateError("only an open account can be frozen")
        self._state = "frozen"
        self._history.append(("freeze", 0, self._balance))

    def unfreeze(self) -> None:
        if self._state != "frozen":
            raise AccountStateError("only a frozen account can be unfrozen")
        self._state = "open"
        self._history.append(("unfreeze", 0, self._balance))

    def close(self) -> None:
        if self._state == "closed":
            raise AccountStateError("account is already closed")
        if self._balance != 0:
            raise AccountStateError("balance must be zero to close")
        self._state = "closed"
        self._history.append(("close", 0, 0))
