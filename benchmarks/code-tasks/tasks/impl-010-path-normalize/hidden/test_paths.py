import unittest

from paths import join_paths, normalize_path


class NormalizeTests(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(normalize_path("a/b/c"), "a/b/c")
        self.assertEqual(normalize_path("/a/b/c"), "/a/b/c")

    def test_collapse_and_dot(self):
        self.assertEqual(normalize_path("a//b///c"), "a/b/c")
        self.assertEqual(normalize_path("./a/./b/."), "a/b")
        self.assertEqual(normalize_path("//a//b"), "/a/b")

    def test_trailing_slash_removed(self):
        self.assertEqual(normalize_path("a/b/"), "a/b")
        self.assertEqual(normalize_path("/a/b/"), "/a/b")

    def test_dotdot_resolution(self):
        self.assertEqual(normalize_path("/a/b/../c"), "/a/c")
        self.assertEqual(normalize_path("a/b/../../c"), "c")
        self.assertEqual(normalize_path("/a/./b/../../c/d/.."), "/c")

    def test_root_cases(self):
        for p in ("/", "//", "///", "/.", "/./", "/a/..", "/..", "/../..", "/a/../.."):
            with self.subTest(p=p):
                self.assertEqual(normalize_path(p), "/")
        self.assertEqual(normalize_path("/../a"), "/a")
        self.assertEqual(normalize_path("/a/../../b"), "/b")

    def test_relative_leading_dotdot_kept(self):
        self.assertEqual(normalize_path("../a"), "../a")
        self.assertEqual(normalize_path("../../a"), "../../a")
        self.assertEqual(normalize_path("a/../../b"), "../b")
        self.assertEqual(normalize_path("../a/../.."), "../..")
        self.assertEqual(normalize_path(".."), "..")

    def test_empty_results_are_dot(self):
        for p in ("", ".", "./", "a/..", "a/b/../..", "./."):
            with self.subTest(p=p):
                self.assertEqual(normalize_path(p), ".")

    def test_opaque_names(self):
        self.assertEqual(normalize_path("a/.../b"), "a/.../b")
        self.assertEqual(normalize_path(".config/../..x/Y"), "..x/Y")
        self.assertEqual(normalize_path("/Foo/BAR"), "/Foo/BAR")


class JoinTests(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(join_paths("/a/b", "../c", "d.txt"), "/a/c/d.txt")
        self.assertEqual(join_paths("a", "b", "c"), "a/b/c")
        self.assertEqual(join_paths("a/", "/b/"), "/b")

    def test_absolute_part_restarts(self):
        self.assertEqual(join_paths("a", "/x", "y"), "/x/y")
        self.assertEqual(join_paths("/a", "b", "/c", "d"), "/c/d")

    def test_empty_parts(self):
        self.assertEqual(join_paths(""), ".")
        self.assertEqual(join_paths("", ""), ".")
        self.assertEqual(join_paths("", "a", "", "b"), "a/b")
        self.assertEqual(join_paths("a", ""), "a")
        self.assertEqual(join_paths("/"), "/")

    def test_dotdot_across_parts(self):
        self.assertEqual(join_paths("a", "..", ".."), "..")
        self.assertEqual(join_paths("/a", "..", ".."), "/")
        self.assertEqual(join_paths("x", "../y"), "y")


if __name__ == "__main__":
    unittest.main()
