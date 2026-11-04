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


class Account:
    def __init__(
        self,
        owner: str,
        overdraft_limit: int = 0,
        daily_withdrawal_limit: int | None = None,
    ) -> None:
        raise NotImplementedError

    @property
    def owner(self) -> str:
        raise NotImplementedError

    @property
    def balance(self) -> int:
        raise NotImplementedError

    @property
    def state(self) -> str:
        raise NotImplementedError

    @property
    def history(self) -> list[tuple[str, int, int]]:
        raise NotImplementedError

    def withdrawn_on(self, day: int) -> int:
        raise NotImplementedError

    def deposit(self, amount: int) -> None:
        raise NotImplementedError

    def withdraw(self, amount: int, day: int) -> None:
        raise NotImplementedError

    def freeze(self) -> None:
        raise NotImplementedError

    def unfreeze(self) -> None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError
