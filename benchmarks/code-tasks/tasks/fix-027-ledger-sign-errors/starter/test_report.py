import unittest

from account import Account
from report import statement


class ReportTests(unittest.TestCase):
    def test_statement_running_balance(self):
        acct = Account("ann")
        acct.book("deposit", 10000)
        acct.book("withdrawal", 2500)
        acct.book("fee", 150)
        self.assertEqual(
            statement(acct),
            [("deposit", 10000, 10000), ("withdrawal", -2500, 7500), ("fee", -150, 7350)],
        )

    def test_balance_after_interest(self):
        acct = Account("bob")
        acct.book("deposit", 1000)
        acct.book("interest", 25)
        self.assertEqual(acct.balance(), 1025)


if __name__ == "__main__":
    unittest.main()
