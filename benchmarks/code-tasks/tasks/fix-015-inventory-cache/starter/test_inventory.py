import unittest

from inventory import Inventory


class InventoryTests(unittest.TestCase):
    def test_total_after_remove(self):
        inv = Inventory()
        inv.add("bolt", 10, 2.5)
        self.assertEqual(inv.total_value(), 25.0)
        inv.remove("bolt", 4)
        self.assertEqual(inv.total_value(), 15.0)

    def test_emptied_sku_is_dropped(self):
        inv = Inventory()
        inv.add("nut", 3, 1.0)
        inv.remove("nut", 3)
        self.assertEqual(inv.sku_count(), 0)


if __name__ == "__main__":
    unittest.main()
