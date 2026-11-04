import unittest

from tags import merge_tags


class TagTests(unittest.TestCase):
    def test_basic_count_order(self):
        self.assertEqual(merge_tags([["a", "b"], ["b", "c"], ["b", "c"]]), ["b", "c", "a"])

    def test_ties_keep_first_occurrence_not_alphabetical(self):
        self.assertEqual(merge_tags([["zeta", "alpha", "mid"]]), ["zeta", "alpha", "mid"])
        self.assertEqual(merge_tags([["b"], ["a"], ["c", "a", "b"]]), ["b", "a", "c"])

    def test_case_insensitive_first_spelling_kept(self):
        self.assertEqual(merge_tags([["Python", "go"], ["PYTHON", "python"], ["Go"]]), ["Python", "go"])
        self.assertEqual(merge_tags([["web"], ["WEB", "Web"]]), ["web"])

    def test_repeats_inside_one_list_count(self):
        self.assertEqual(merge_tags([["x", "y", "y"], ["x"]]), ["x", "y"])
        self.assertEqual(merge_tags([["x", "y", "y"]]), ["y", "x"])

    def test_strip_and_empty(self):
        self.assertEqual(merge_tags([["  a ", "", "   ", "\tb\n"], ["A"]]), ["a", "b"])
        self.assertEqual(merge_tags([["a b", "a  b"]]), ["a b", "a  b"])

    def test_unicode_equivalence(self):
        composed, decomposed = "café", "café"
        out = merge_tags([[decomposed], [composed], [composed.upper()]])
        self.assertEqual(out, [decomposed])
        self.assertEqual(merge_tags([["Straße"], ["STRASSE"]]), ["Straße"])
        self.assertEqual(merge_tags([["\u212bX"], ["\u00c5x"]]), ["\u212bX"])

    def test_not_nfkc(self):
        # compatibility characters are NOT folded together
        self.assertEqual(merge_tags([["x\u00b2"], ["x2"]]), ["x\u00b2", "x2"])

    def test_limit(self):
        data = [["a", "b", "b", "c"]]
        self.assertEqual(merge_tags(data, 2), ["b", "a"])
        self.assertEqual(merge_tags(data, 0), [])
        self.assertEqual(merge_tags(data, None), ["b", "a", "c"])
        self.assertEqual(merge_tags(data, 10), ["b", "a", "c"])

    def test_empty_inputs(self):
        self.assertEqual(merge_tags([]), [])
        self.assertEqual(merge_tags([[], [""]]), [])
        self.assertEqual(merge_tags([], 0), [])

    def test_errors(self):
        with self.assertRaises(ValueError):
            merge_tags([["a"]], -1)
        with self.assertRaises(TypeError):
            merge_tags([["a"]], True)
        with self.assertRaises(TypeError):
            merge_tags([["a"]], "2")
        with self.assertRaises(TypeError):
            merge_tags([["a", 3]])

    def test_input_not_modified(self):
        data = [["B", "a"], ["b"]]
        merge_tags(data)
        self.assertEqual(data, [["B", "a"], ["b"]])


if __name__ == "__main__":
    unittest.main()
