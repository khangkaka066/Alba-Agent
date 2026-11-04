import unittest

from ledger.accounts import Account, InsufficientFunds
from ledger.money import format_cents, to_cents


class LedgerTests(unittest.TestCase):
    def test_to_cents_is_exact(self):
        self.assertEqual(to_cents("0.29"), 29)
        self.assertEqual(to_cents("12.34"), 1234)

    def test_format_negative(self):
        self.assertEqual(format_cents(-5), "-0.05")

    def test_withdraw_exact_balance(self):
        account = Account("a", 500)
        account.withdraw(500, 1)
        self.assertEqual(account.balance, 0)
        with self.assertRaises(InsufficientFunds):
            account.withdraw(1, 2)


if __name__ == "__main__":
    unittest.main()
