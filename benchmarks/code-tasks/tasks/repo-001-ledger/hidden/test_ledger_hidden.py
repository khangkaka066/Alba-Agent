import unittest

from ledger.accounts import Account, ClosedAccount, InsufficientFunds
from ledger.money import format_cents, to_cents
from ledger.statement import statement
from ledger.transfer import transfer


class MoneyTests(unittest.TestCase):
    def test_to_cents_values(self):
        for text, cents in [("0.29", 29), ("1.15", 115), ("19.99", 1999), ("5", 500), ("-0.29", -29),
                            ("1,234.50", 123450), (" 7.1 ", 710), ("0.07", 7), ("4.35", 435), ("2.675", None)]:
            if cents is None:
                with self.assertRaises(ValueError):
                    to_cents(text)
            else:
                self.assertEqual(to_cents(text), cents, text)

    def test_to_cents_rejects_garbage(self):
        for text in ["", "abc", "nan", "inf", "-inf", "1.2.3", "12.345", "$5"]:
            with self.assertRaises(ValueError, msg=text):
                to_cents(text)

    def test_two_decimals_with_trailing_zero_is_fine(self):
        self.assertEqual(to_cents("3.10"), 310)

    def test_format(self):
        self.assertEqual(format_cents(1234567), "12,345.67")
        self.assertEqual(format_cents(0), "0.00")
        self.assertEqual(format_cents(-5), "-0.05")
        self.assertEqual(format_cents(-123456), "-1,234.56")


class AccountTests(unittest.TestCase):
    def test_withdraw_rules(self):
        account = Account("a", 100)
        account.withdraw(100, 1)
        self.assertEqual(account.balance, 0)
        self.assertEqual(account.history, [("withdraw", 100, 1)])
        with self.assertRaises(InsufficientFunds):
            account.withdraw(1, 2)
        with self.assertRaises(ValueError):
            account.withdraw(0, 2)
        with self.assertRaises(ValueError):
            account.withdraw(True and 1.5, 2)

    def test_closed(self):
        account = Account("a", 100)
        account.close()
        with self.assertRaises(ClosedAccount):
            account.deposit(5, 1)
        with self.assertRaises(ClosedAccount):
            account.withdraw(5, 1)
        with self.assertRaises(ValueError):
            account.deposit(-5, 1)


class TransferTests(unittest.TestCase):
    def test_success(self):
        a, b = Account("a", 1000), Account("b", 0)
        transfer(a, b, 250, 3)
        self.assertEqual((a.balance, b.balance), (750, 250))
        self.assertEqual(a.history, [("withdraw", 250, 3)])
        self.assertEqual(b.history, [("deposit", 250, 3)])

    def test_closed_target_changes_nothing(self):
        a, b = Account("a", 1000), Account("b", 0)
        b.close()
        with self.assertRaises(ClosedAccount):
            transfer(a, b, 250, 3)
        self.assertEqual(a.balance, 1000)
        self.assertEqual(a.history, [])
        self.assertEqual((b.balance, b.history), (0, []))

    def test_insufficient_changes_nothing(self):
        a, b = Account("a", 100), Account("b", 0)
        with self.assertRaises(InsufficientFunds):
            transfer(a, b, 101, 3)
        self.assertEqual((a.balance, a.history, b.balance, b.history), (100, [], 0, []))

    def test_rollback_keeps_earlier_history(self):
        a, b = Account("a", 1000), Account("b", 0)
        a.deposit(10, 1)
        b.close()
        with self.assertRaises(ClosedAccount):
            transfer(a, b, 5, 2)
        self.assertEqual(a.history, [("deposit", 10, 1)])
        self.assertEqual(a.balance, 1010)

    def test_same_account_and_bad_amount(self):
        a = Account("a", 100)
        with self.assertRaises(ValueError):
            transfer(a, a, 10, 1)
        with self.assertRaises(ValueError):
            transfer(a, Account("b"), 0, 1)
        self.assertEqual((a.balance, a.history), (100, []))


class StatementTests(unittest.TestCase):
    def test_sorted_with_running_balance(self):
        account = Account("a", 1000)
        account.deposit(500, 5)
        account.withdraw(200, 2)
        account.deposit(100, 5)
        self.assertEqual(statement(account), [
            "2 withdraw 2.00 8.00",
            "5 deposit 5.00 13.00",
            "5 deposit 1.00 14.00",
        ])

    def test_no_history(self):
        self.assertEqual(statement(Account("a", 5)), [])

    def test_opening_balance_and_thousands(self):
        account = Account("a", 0)
        account.deposit(123456, 1)
        self.assertEqual(statement(account), ["1 deposit 1,234.56 1,234.56"])


if __name__ == "__main__":
    unittest.main()
