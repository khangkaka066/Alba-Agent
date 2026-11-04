import unittest

from tasks import CycleError, build_order


class TaskTests(unittest.TestCase):
    def test_chain(self):
        self.assertEqual(build_order({"deploy": ["test"], "test": ["build"], "build": []}), ["build", "test", "deploy"])

    def test_diamond_is_not_a_cycle(self):
        deps = {"app": ["lib_a", "lib_b"], "lib_a": ["core"], "lib_b": ["core"]}
        self.assertEqual(build_order(deps), ["core", "lib_a", "lib_b", "app"])

    def test_real_cycle(self):
        with self.assertRaises(CycleError):
            build_order({"a": ["b"], "b": ["a"]})


if __name__ == "__main__":
    unittest.main()
