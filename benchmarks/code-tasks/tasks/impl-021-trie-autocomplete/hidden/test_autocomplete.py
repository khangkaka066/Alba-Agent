import unittest

from autocomplete import Autocomplete


def build():
    ac = Autocomplete()
    for word, weight in [("car", 10), ("card", 5), ("care", 5), ("cart", 7), ("cat", 20), ("dog", 3)]:
        ac.add(word, weight)
    return ac


class AutocompleteTests(unittest.TestCase):
    def test_suggest_orders_by_weight_then_alpha(self):
        ac = build()
        self.assertEqual(ac.suggest("car"), ["car", "cart", "card", "care"])
        self.assertEqual(ac.suggest("c"), ["cat", "car", "cart", "card", "care"])
        self.assertEqual(ac.suggest("c", limit=2), ["cat", "car"])

    def test_empty_prefix_and_no_match(self):
        ac = build()
        self.assertEqual(ac.suggest("", limit=3), ["cat", "car", "cart"])
        self.assertEqual(ac.suggest("", limit=100), ["cat", "car", "cart", "card", "care", "dog"])
        self.assertEqual(ac.suggest("x"), [])
        self.assertEqual(ac.suggest("cats"), [])

    def test_word_is_its_own_prefix(self):
        ac = build()
        self.assertEqual(ac.suggest("dog"), ["dog"])
        self.assertEqual(ac.suggest("cat"), ["cat"])

    def test_add_accumulates_weight(self):
        ac = build()
        ac.add("dog", 40)
        self.assertEqual(ac.weight_of("dog"), 43)
        self.assertEqual(ac.suggest("")[0], "dog")
        self.assertEqual(len(ac), 6)
        ac.add("owl")
        self.assertEqual(ac.weight_of("owl"), 1)
        self.assertEqual(len(ac), 7)

    def test_limit_zero_and_invalid(self):
        ac = build()
        self.assertEqual(ac.suggest("c", limit=0), [])
        with self.assertRaises(ValueError):
            ac.suggest("c", limit=-1)

    def test_add_validation(self):
        ac = Autocomplete()
        for word, weight in [("", 1), ("a", 0), ("a", -2)]:
            with self.assertRaises(ValueError):
                ac.add(word, weight)
        self.assertEqual(len(ac), 0)
        self.assertEqual(ac.suggest(""), [])

    def test_remove_keeps_neighbours(self):
        ac = build()
        self.assertTrue(ac.remove("car"))
        self.assertFalse(ac.remove("car"))
        self.assertNotIn("car", ac)
        self.assertIn("card", ac)
        self.assertEqual(ac.suggest("car"), ["cart", "card", "care"])
        self.assertEqual(len(ac), 5)
        self.assertFalse(ac.remove("ca"))  # only a prefix, never a word
        self.assertFalse(ac.remove("zebra"))
        self.assertFalse(ac.remove(""))

    def test_readd_after_remove_resets_weight(self):
        ac = build()
        ac.remove("cat")
        ac.add("cat", 2)
        self.assertEqual(ac.weight_of("cat"), 2)
        self.assertEqual(ac.suggest("ca")[:2], ["car", "cart"])

    def test_contains_and_weight_of(self):
        ac = build()
        self.assertIn("cart", ac)
        self.assertNotIn("ca", ac)
        self.assertNotIn("", ac)
        self.assertEqual(ac.weight_of("card"), 5)
        with self.assertRaises(KeyError):
            ac.weight_of("ca")
        with self.assertRaises(KeyError):
            ac.weight_of("nope")

    def test_count_prefix(self):
        ac = build()
        self.assertEqual(ac.count_prefix("car"), 4)
        self.assertEqual(ac.count_prefix("c"), 5)
        self.assertEqual(ac.count_prefix(""), 6)
        self.assertEqual(ac.count_prefix("q"), 0)
        ac.remove("card")
        self.assertEqual(ac.count_prefix("car"), 3)

    def test_case_sensitive_and_unicode(self):
        ac = Autocomplete()
        ac.add("Apple", 2)
        ac.add("apple", 1)
        ac.add("äpfel", 1)
        self.assertEqual(ac.suggest("a"), ["apple"])
        self.assertEqual(ac.suggest("A"), ["Apple"])
        self.assertEqual(ac.suggest("ä"), ["äpfel"])
        self.assertEqual(ac.suggest(""), ["Apple", "apple", "äpfel"])

    def test_larger_vocabulary(self):
        ac = Autocomplete()
        for i in range(20000):
            ac.add(f"word{i:05d}", i % 7 + 1)
        self.assertEqual(len(ac), 20000)
        self.assertEqual(ac.count_prefix("word0001"), 10)
        top = ac.suggest("word0001", limit=3)
        # weight is i % 7 + 1; among word0001x, i=10015..: highest weights first, ties alphabetical
        expected = sorted((f"word0001{d}" for d in range(10)), key=lambda w: (-(int(w[4:]) % 7 + 1), w))[:3]
        self.assertEqual(top, expected)
        self.assertEqual(len(top), 3)
        weights = [ac.weight_of(w) for w in top]
        self.assertEqual(weights, sorted(weights, reverse=True))


if __name__ == "__main__":
    unittest.main()
