import unittest

from account import Account, InsufficientFunds, transfer
from ledger import Entry
from report import format_cents, render, statement


class LedgerHiddenTests(unittest.TestCase):
    def test_signs_of_every_kind(self):
        for kind in ("deposit", "interest", "transfer_in"):
            self.assertEqual(Entry(kind, 7).signed, 7)
        for kind in ("withdrawal", "transfer_out", "fee"):
            self.assertEqual(Entry(kind, 7).signed, -7)

    def test_fee_reduces_balance(self):
        acct = Account("a")
        acct.book("deposit", 500)
        acct.book("fee", 120)
        self.assertEqual(acct.balance(), 380)

    def test_fee_may_overdraw_but_withdrawal_may_not(self):
        acct = Account("a")
        acct.book("deposit", 100)
        acct.book("fee", 250)
        self.assertEqual(acct.balance(), -150)
        with self.assertRaises(InsufficientFunds):
            acct.book("withdrawal", 1)
        self.assertEqual(len(acct.entries), 2)

    def test_withdrawal_to_exactly_zero_allowed(self):
        acct = Account("a")
        acct.book("deposit", 300)
        acct.book("withdrawal", 300)
        self.assertEqual(acct.balance(), 0)

    def test_transfer_moves_money_and_fails_atomically(self):
        a, b = Account("a"), Account("b")
        a.book("deposit", 1000)
        transfer(a, b, 400)
        self.assertEqual((a.balance(), b.balance()), (600, 400))
        with self.assertRaises(InsufficientFunds):
            transfer(a, b, 601)
        self.assertEqual((a.balance(), b.balance()), (600, 400))

    def test_statement_with_all_kinds(self):
        acct = Account("a")
        for kind, cents in [("deposit", 5000), ("fee", 200), ("interest", 30), ("transfer_out", 1000), ("transfer_in", 70), ("withdrawal", 100)]:
            acct.book(kind, cents)
        rows = statement(acct)
        self.assertEqual([r[2] for r in rows], [5000, 4800, 4830, 3830, 3900, 3800])
        self.assertEqual(rows[-1][2], acct.balance())

    def test_render_and_format_cents(self):
        acct = Account("a")
        acct.book("deposit", 1050)
        acct.book("fee", 1100)
        text = render(acct)
        self.assertEqual(text.splitlines()[-1].split(), ["balance", "-0.50"])
        self.assertEqual(text.splitlines()[1].split(), ["fee", "-11.00", "-0.50"])
        self.assertEqual(format_cents(12345), "123.45")
        self.assertEqual(format_cents(-5), "-0.05")
        self.assertEqual(format_cents(0), "0.00")

    def test_invalid_entries(self):
        with self.assertRaises(ValueError):
            Entry("bonus", 5)
        with self.assertRaises(ValueError):
            Entry("deposit", 0)
        with self.assertRaises(ValueError):
            Entry("deposit", 1.5)


if __name__ == "__main__":
    unittest.main()
