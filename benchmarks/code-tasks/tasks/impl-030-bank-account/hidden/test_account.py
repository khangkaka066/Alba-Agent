import unittest

from account import (
    OVERDRAFT_FEE,
    Account,
    AccountError,
    AccountStateError,
    DailyLimitError,
    InsufficientFundsError,
)


class AccountTests(unittest.TestCase):
    def test_new_account(self):
        a = Account("ann")
        self.assertEqual((a.owner, a.balance, a.state, a.history), ("ann", 0, "open", []))
        self.assertEqual(OVERDRAFT_FEE, 500)

    def test_exception_hierarchy(self):
        for cls in (AccountStateError, InsufficientFundsError, DailyLimitError):
            self.assertTrue(issubclass(cls, AccountError))
        self.assertTrue(issubclass(AccountError, Exception))

    def test_constructor_validation(self):
        for kwargs in ({"overdraft_limit": -1}, {"daily_withdrawal_limit": 0}, {"daily_withdrawal_limit": -5}):
            with self.assertRaises(ValueError):
                Account("x", **kwargs)

    def test_deposit_and_withdraw_basic(self):
        a = Account("ann")
        a.deposit(1000)
        a.withdraw(300, day=1)
        self.assertEqual(a.balance, 700)
        a.withdraw(700, day=1)
        self.assertEqual(a.balance, 0)
        self.assertEqual(
            a.history,
            [("deposit", 1000, 1000), ("withdraw", 300, 700), ("withdraw", 700, 0)],
        )

    def test_amount_validation_comes_first(self):
        a = Account("ann")
        a.close()  # closed: but validation errors must still win
        for bad in (1.5, "5", None, True):
            with self.assertRaises(TypeError):
                a.deposit(bad)
            with self.assertRaises(TypeError):
                a.withdraw(bad, 1)
        for bad in (0, -10):
            with self.assertRaises(ValueError):
                a.deposit(bad)
            with self.assertRaises(ValueError):
                a.withdraw(bad, 1)

    def test_day_must_be_int(self):
        a = Account("ann")
        a.deposit(100)
        for bad in (1.0, "1", None):
            with self.assertRaises(TypeError):
                a.withdraw(10, bad)
        self.assertEqual(a.balance, 100)

    def test_no_overdraft_by_default(self):
        a = Account("ann")
        a.deposit(100)
        with self.assertRaises(InsufficientFundsError):
            a.withdraw(101, 1)
        self.assertEqual(a.balance, 100)
        self.assertEqual(len(a.history), 1)
        self.assertEqual(a.withdrawn_on(1), 0)

    def test_overdraft_fee_charged_once_when_crossing_zero(self):
        a = Account("ann", overdraft_limit=2000)
        a.deposit(1000)
        a.withdraw(1500, 1)
        self.assertEqual(a.balance, -500 - OVERDRAFT_FEE)
        self.assertEqual(
            a.history,
            [("deposit", 1000, 1000), ("withdraw", 1500, -500), ("fee", 500, -1000)],
        )
        a.withdraw(300, 1)  # already overdrawn: no second fee
        self.assertEqual(a.balance, -1300)
        self.assertEqual(a.history[-1], ("withdraw", 300, -1300))
        self.assertEqual(a.withdrawn_on(1), 1800)  # the fee is not counted

    def test_fee_from_exactly_zero_balance(self):
        a = Account("ann", overdraft_limit=1000)
        a.withdraw(100, 1)  # balance was 0 (>= 0) and ends negative: fee applies
        self.assertEqual(a.balance, -600)
        self.assertEqual(a.history, [("withdraw", 100, -100), ("fee", 500, -600)])

    def test_no_fee_when_balance_lands_exactly_on_zero(self):
        a = Account("ann", overdraft_limit=1000)
        a.deposit(100)
        a.withdraw(100, 1)
        self.assertEqual(a.balance, 0)
        self.assertEqual(len(a.history), 2)

    def test_fee_counts_towards_overdraft_limit(self):
        a = Account("ann", overdraft_limit=1000)
        a.deposit(100)
        with self.assertRaises(InsufficientFundsError):
            a.withdraw(700, 1)  # after = -600, fee 500 -> -1100 < -1000
        self.assertEqual(a.balance, 100)
        a.withdraw(600, 1)  # after = -500, fee 500 -> -1000: exactly the limit
        self.assertEqual(a.balance, -1000)
        with self.assertRaises(InsufficientFundsError):
            a.withdraw(1, 1)  # already overdrawn: no fee, but -1001 < -1000
        self.assertEqual(a.balance, -1000)

    def test_deposit_into_overdrawn_account(self):
        a = Account("ann", overdraft_limit=1000)
        a.withdraw(100, 1)  # -600
        a.deposit(200)
        self.assertEqual(a.balance, -400)
        a.deposit(400)
        self.assertEqual(a.balance, 0)
        a.withdraw(50, 2)  # back at >= 0, crossing again: a new fee
        self.assertEqual(a.balance, -550)

    def test_daily_limit(self):
        a = Account("ann", daily_withdrawal_limit=1000)
        a.deposit(5000)
        a.withdraw(600, 1)
        with self.assertRaises(DailyLimitError):
            a.withdraw(401, 1)
        a.withdraw(400, 1)  # exactly reaching the limit is fine
        self.assertEqual(a.withdrawn_on(1), 1000)
        with self.assertRaises(DailyLimitError):
            a.withdraw(1, 1)
        a.withdraw(1000, 2)  # a new day
        self.assertEqual(a.balance, 3000)
        self.assertEqual(a.withdrawn_on(2), 1000)
        self.assertEqual(a.withdrawn_on(99), 0)

    def test_failed_withdrawals_do_not_count_towards_daily_total(self):
        a = Account("ann", daily_withdrawal_limit=500)
        a.deposit(300)
        with self.assertRaises(InsufficientFundsError):
            a.withdraw(400, 1)
        self.assertEqual(a.withdrawn_on(1), 0)
        a.withdraw(300, 1)
        self.assertEqual(a.withdrawn_on(1), 300)

    def test_daily_limit_checked_before_funds(self):
        a = Account("ann", daily_withdrawal_limit=100)
        with self.assertRaises(DailyLimitError):
            a.withdraw(500, 1)  # also insufficient, but the limit error comes first
        a2 = Account("bob", daily_withdrawal_limit=1000)
        with self.assertRaises(InsufficientFundsError):
            a2.withdraw(500, 1)

    def test_freeze_and_unfreeze(self):
        a = Account("ann")
        a.deposit(1000)
        a.freeze()
        self.assertEqual(a.state, "frozen")
        a.deposit(50)  # deposits still allowed
        self.assertEqual(a.balance, 1050)
        with self.assertRaises(AccountStateError):
            a.withdraw(10, 1)
        with self.assertRaises(AccountStateError):
            a.freeze()
        a.unfreeze()
        self.assertEqual(a.state, "open")
        a.withdraw(10, 1)
        with self.assertRaises(AccountStateError):
            a.unfreeze()
        self.assertEqual(
            [h[0] for h in a.history],
            ["deposit", "freeze", "deposit", "unfreeze", "withdraw"],
        )
        self.assertEqual(a.history[1], ("freeze", 0, 1000))

    def test_close_rules(self):
        a = Account("ann", overdraft_limit=1000)
        a.deposit(10)
        with self.assertRaises(AccountStateError):
            a.close()
        a.withdraw(10, 1)
        a.freeze()
        a.close()  # frozen accounts can be closed when empty
        self.assertEqual(a.state, "closed")
        self.assertEqual(a.history[-1], ("close", 0, 0))
        for call in (a.close, a.freeze, a.unfreeze, lambda: a.deposit(1), lambda: a.withdraw(1, 1)):
            with self.assertRaises(AccountStateError):
                call()
        self.assertEqual(a.state, "closed")

    def test_cannot_close_with_negative_balance(self):
        a = Account("ann", overdraft_limit=1000)
        a.withdraw(100, 1)
        with self.assertRaises(AccountStateError):
            a.close()
        self.assertEqual(a.state, "open")

    def test_withdraw_from_closed_reports_state_error_not_funds(self):
        a = Account("ann", daily_withdrawal_limit=1)
        a.close()
        with self.assertRaises(AccountStateError):
            a.withdraw(100, 1)

    def test_history_is_a_copy(self):
        a = Account("ann")
        a.deposit(5)
        a.history.append(("junk", 0, 0))
        self.assertEqual(a.history, [("deposit", 5, 5)])


if __name__ == "__main__":
    unittest.main()
