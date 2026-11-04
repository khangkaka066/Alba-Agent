import unittest

from topo import CycleError, execution_levels, topological_order


class TopologicalOrderTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(topological_order({}), [])

    def test_chain(self):
        self.assertEqual(topological_order({"c": ["b"], "b": ["a"], "a": []}), ["a", "b", "c"])

    def test_lexicographically_smallest(self):
        deps = {"d": ["b", "c"], "c": ["a"], "b": ["a"], "a": [], "e": []}
        self.assertEqual(topological_order(deps), ["a", "b", "c", "d", "e"])
        # "z" has no dependencies but must still wait its turn alphabetically; "b" needs "z"
        self.assertEqual(topological_order({"b": ["z"], "a": [], "c": []}), ["a", "c", "z", "b"])

    def test_implicit_tasks_from_dependency_lists(self):
        self.assertEqual(topological_order({"app": ["lib", "util"]}), ["lib", "util", "app"])

    def test_duplicates_in_dependency_list(self):
        self.assertEqual(topological_order({"b": ["a", "a", "a"]}), ["a", "b"])

    def test_isolated_tasks_sorted(self):
        self.assertEqual(topological_order({"q": [], "m": [], "x": []}), ["m", "q", "x"])

    def test_input_not_modified(self):
        deps = {"b": ["a"], "a": []}
        topological_order(deps)
        execution_levels(deps)
        self.assertEqual(deps, {"b": ["a"], "a": []})

    def test_cycles(self):
        for deps in [{"a": ["a"]}, {"a": ["b"], "b": ["a"]}, {"a": [], "b": ["c"], "c": ["d"], "d": ["b"]},
                     {"x": ["y"], "y": ["z"], "z": ["x"], "ok": []}]:
            with self.subTest(deps=deps):
                with self.assertRaises(CycleError):
                    topological_order(deps)
                with self.assertRaises(CycleError):
                    execution_levels(deps)

    def test_cycle_error_is_value_error(self):
        self.assertTrue(issubclass(CycleError, ValueError))

    def test_larger_graph(self):
        deps = {
            "deploy": ["test", "package"], "package": ["build"], "test": ["build", "lint"],
            "build": ["deps"], "lint": ["deps"], "deps": [], "docs": ["build"],
        }
        order = topological_order(deps)
        self.assertEqual(order, ["deps", "build", "docs", "lint", "package", "test", "deploy"])


class ExecutionLevelsTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(execution_levels({}), [])

    def test_levels(self):
        deps = {"d": ["b", "c"], "c": ["a"], "b": ["a"], "a": [], "e": []}
        self.assertEqual(execution_levels(deps), [["a", "e"], ["b", "c"], ["d"]])

    def test_level_is_longest_path(self):
        deps = {"c": ["a", "b"], "b": ["a"], "a": []}
        self.assertEqual(execution_levels(deps), [["a"], ["b"], ["c"]])
        deps = {"x": ["a"], "y": ["x", "a"], "a": []}
        self.assertEqual(execution_levels(deps), [["a"], ["x"], ["y"]])

    def test_implicit_and_sorted(self):
        self.assertEqual(execution_levels({"t": ["z", "m"], "s": ["m"]}), [["m", "z"], ["s", "t"]])


if __name__ == "__main__":
    unittest.main()
