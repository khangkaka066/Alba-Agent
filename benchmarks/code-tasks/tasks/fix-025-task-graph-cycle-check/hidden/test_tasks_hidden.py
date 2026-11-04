import unittest

from graph import DiGraph
from tasks import CycleError, build_order, levels
from toposort import postorder


class TaskHiddenTests(unittest.TestCase):
    def test_diamond_with_shared_dependency_chain(self):
        deps = {"top": ["l", "r"], "l": ["mid"], "r": ["mid"], "mid": ["base"]}
        self.assertEqual(build_order(deps), ["base", "mid", "l", "r", "top"])

    def test_independent_tasks_follow_dict_order(self):
        self.assertEqual(build_order({"b": [], "a": [], "c": []}), ["b", "a", "c"])

    def test_dependency_only_nodes_are_included(self):
        self.assertEqual(build_order({"app": ["libx", "liby"]}), ["libx", "liby", "app"])

    def test_later_task_that_is_already_done(self):
        deps = {"a": ["c"], "b": ["c"], "c": []}
        self.assertEqual(build_order(deps), ["c", "a", "b"])

    def test_cycle_reports_path(self):
        with self.assertRaises(CycleError) as ctx:
            build_order({"a": ["b"], "b": ["c"], "c": ["a"]})
        self.assertEqual(ctx.exception.cycle, ["a", "b", "c", "a"])

    def test_cycle_found_after_a_done_prefix(self):
        deps = {"ok": [], "x": ["ok", "y"], "y": ["z"], "z": ["y"]}
        with self.assertRaises(CycleError) as ctx:
            build_order(deps)
        self.assertEqual(ctx.exception.cycle, ["y", "z", "y"])

    def test_self_dependency_is_a_cycle(self):
        with self.assertRaises(CycleError) as ctx:
            build_order({"a": ["a"]})
        self.assertEqual(ctx.exception.cycle, ["a", "a"])

    def test_levels(self):
        deps = {"app": ["lib_a", "lib_b"], "lib_a": ["core"], "lib_b": ["core"], "docs": []}
        self.assertEqual(levels(deps), [["core", "docs"], ["lib_a", "lib_b"], ["app"]])
        self.assertEqual(levels({}), [])

    def test_wide_graph_many_shared_dependencies(self):
        deps = {f"t{i}": ["shared1", "shared2"] for i in range(20)}
        order = build_order(deps)
        self.assertEqual(order[:2], ["shared1", "shared2"])
        self.assertEqual(len(order), 22)

    def test_graph_level_postorder_with_revisits(self):
        g = DiGraph()
        for src, dst in [("a", "b"), ("a", "c"), ("b", "d"), ("c", "d"), ("d", "e"), ("c", "e")]:
            g.add_edge(src, dst)
        self.assertEqual(postorder(g), ["e", "d", "b", "c", "a"])


if __name__ == "__main__":
    unittest.main()
