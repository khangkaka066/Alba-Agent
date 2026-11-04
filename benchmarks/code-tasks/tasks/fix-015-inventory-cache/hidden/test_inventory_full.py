import unittest

from inventory import Inventory


def stocked():
    inv = Inventory()
    inv.add("bolt", 10, 2.5)
    inv.add("nut", 4, 0.5)
    return inv


class InventoryFullTests(unittest.TestCase):
    def test_total(self):
        inv = stocked()
        self.assertEqual(inv.total_value(), 27.0)
        self.assertEqual(inv.total_value(), 27.0)

    def test_total_after_add(self):
        inv = stocked()
        inv.total_value()
        inv.add("nut", 2, 1.0)
        self.assertEqual(inv.total_value(), 10 * 2.5 + 6 * 1.0)

    def test_total_after_remove(self):
        inv = stocked()
        inv.total_value()
        inv.remove("bolt", 4)
        self.assertEqual(inv.total_value(), 17.0)

    def test_total_after_set_price(self):
        inv = stocked()
        inv.total_value()
        inv.set_price("nut", 2.0)
        self.assertEqual(inv.total_value(), 33.0)

    def test_set_price_unknown(self):
        with self.assertRaises(KeyError):
            stocked().set_price("gear", 1.0)

    def test_emptied_sku_is_dropped(self):
        inv = stocked()
        inv.remove("nut", 4)
        self.assertEqual(inv.sku_count(), 1)
        self.assertEqual(inv.quantity("nut"), 0)
        self.assertEqual(inv.total_value(), 25.0)

    def test_dropped_sku_can_be_added_again(self):
        inv = stocked()
        inv.remove("nut", 4)
        inv.add("nut", 1, 3.0)
        self.assertEqual(inv.sku_count(), 2)
        self.assertEqual(inv.total_value(), 28.0)

    def test_remove_too_much(self):
        inv = stocked()
        inv.total_value()
        with self.assertRaises(ValueError):
            inv.remove("nut", 5)
        with self.assertRaises(ValueError):
            inv.remove("ghost", 1)
        self.assertEqual(inv.quantity("nut"), 4)
        self.assertEqual(inv.total_value(), 27.0)

    def test_empty_inventory(self):
        inv = Inventory()
        self.assertEqual(inv.total_value(), 0)
        self.assertEqual(inv.sku_count(), 0)

    def test_interleaved_operations(self):
        inv = Inventory()
        inv.add("a", 2, 10.0)
        self.assertEqual(inv.total_value(), 20.0)
        inv.set_price("a", 12.5)
        self.assertEqual(inv.total_value(), 25.0)
        inv.remove("a", 1)
        self.assertEqual(inv.total_value(), 12.5)
        inv.remove("a", 1)
        self.assertEqual(inv.total_value(), 0)
        self.assertEqual(inv.sku_count(), 0)


if __name__ == "__main__":
    unittest.main()
