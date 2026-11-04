Implement the `Account` class and its exceptions in `account.py`: the core ledger rules of a small retail bank. All money is an integer number of cents. Time is never read; callers pass a `day` number (an int) to `withdraw`.

**Exceptions** (all in `account.py`): `AccountError(Exception)` is the base class; `AccountStateError`, `InsufficientFundsError` and `DailyLimitError` are subclasses of it. Module constant `OVERDRAFT_FEE = 500`.

**Construction.** `Account(owner, overdraft_limit=0, daily_withdrawal_limit=None)`. `overdraft_limit` is an int >= 0: how far below zero the balance may go. `daily_withdrawal_limit` is `None` (no limit) or an int >= 1. Invalid values raise `ValueError`. A new account has balance `0` and state `"open"`.

**States.** `"open"`, `"frozen"`, `"closed"` (strings, exposed as `account.state`). `account.balance` is the current balance in cents, `account.owner` the owner.

**Operations.** For `deposit(amount)` and `withdraw(amount, day)` the amount is validated first, before anything else: a non-int amount (floats and bools included) raises `TypeError`, an int <= 0 raises `ValueError`. `day` for `withdraw` must be an int, otherwise `TypeError`.
- `deposit(amount)`: allowed while the account is `"open"` or `"frozen"`; on a `"closed"` account it raises `AccountStateError`. Increases the balance (this can leave an overdrawn balance still negative).
- `withdraw(amount, day)`: only allowed while `"open"`, otherwise `AccountStateError` (frozen and closed accounts both refuse). Then, in this order:
  1. Daily limit: if a limit is set and the total already withdrawn on that same `day` plus `amount` is greater than the limit, raise `DailyLimitError`. (A withdrawal exactly reaching the limit is fine.)
  2. Funds: let `after = balance - amount`. An **overdraft fee** of `OVERDRAFT_FEE` is charged when the balance was `>= 0` before the withdrawal and `after < 0`; otherwise there is no fee (so no second fee while already overdrawn). If `after - fee < -overdraft_limit`, raise `InsufficientFundsError`. The fee counts towards that check.
  On success the balance becomes `after - fee`. Only the withdrawn `amount` (not the fee) counts towards the day's total, and only successful withdrawals count at all. `account.withdrawn_on(day)` returns the total successfully withdrawn on that day (`0` for an unknown day).
- `freeze()`: allowed only from `"open"`; otherwise `AccountStateError`. `unfreeze()`: allowed only from `"frozen"`, otherwise `AccountStateError`. Freezing keeps the balance as it is.
- `close()`: allowed from `"open"` or `"frozen"`, and only when the balance is exactly `0`; otherwise `AccountStateError` (already closed, or non-zero balance including a negative one). A closed account stays closed forever.

**History.** `account.history` returns a new list of `(kind, amount, balance_after)` tuples, one per successful operation, in order: `("deposit", amount, balance)`, `("withdraw", amount, balance)` where the recorded balance is the balance after subtracting just the amount, followed by an extra `("fee", OVERDRAFT_FEE, balance)` entry (balance after the fee) if a fee was charged, and `("freeze", 0, balance)`, `("unfreeze", 0, balance)`, `("close", 0, 0)`. A failed operation changes nothing (balance, state, daily totals, history) and records nothing.
