import copy
import unittest

from loader import DEFAULTS, apply_env, load_config
from merge import deep_merge


class LoaderHiddenTests(unittest.TestCase):
    def test_defaults_untouched_after_many_loads(self):
        snapshot = copy.deepcopy(DEFAULTS)
        load_config(env={"APP_DB__HOST": "h", "APP_CACHE__TTL": "1", "APP_NEW__LEVEL__X": "y"})
        cfg = load_config({"db": {"options": {"pool": 9}}})
        cfg["db"]["options"]["pool"] = 99
        cfg["features"].append("x")
        self.assertEqual(DEFAULTS, snapshot)
        self.assertEqual(load_config(), snapshot)

    def test_override_inputs_not_mutated_or_aliased(self):
        overrides = {"db": {"extra": {"a": [1, 2]}}, "tags": ["x"]}
        before = copy.deepcopy(overrides)
        cfg = load_config(overrides, env={"APP_DB__EXTRA__B": "1", "APP_TAGS": "replaced"})
        self.assertEqual(overrides, before)
        cfg2 = load_config(overrides)
        cfg2["db"]["extra"]["a"].append(3)
        cfg2["tags"].append("y")
        self.assertEqual(overrides, before)
        self.assertEqual(cfg["tags"], "replaced")

    def test_none_removes_keys_including_nested(self):
        cfg = load_config({"cache": None, "db": {"options": {"pool": None, "ssl": True}}})
        self.assertNotIn("cache", cfg)
        self.assertEqual(cfg["db"]["options"], {"ssl": True})

    def test_none_for_missing_key_and_inside_new_dict(self):
        merged = deep_merge({"a": 1}, {"missing": None, "new": {"keep": 1, "drop": None}})
        self.assertEqual(merged, {"a": 1, "new": {"keep": 1}})

    def test_dict_replaced_by_scalar_and_back(self):
        self.assertEqual(deep_merge({"a": {"b": 1}}, {"a": 5}), {"a": 5})
        self.assertEqual(deep_merge({"a": 5}, {"a": {"b": {"c": None, "d": 1}}}), {"a": {"b": {"d": 1}}})

    def test_lists_replace_and_are_copied(self):
        base = {"features": ["a", "b"]}
        merged = deep_merge(base, {})
        merged["features"].append("c")
        self.assertEqual(base["features"], ["a", "b"])
        self.assertEqual(deep_merge(base, {"features": ["z"]}), {"features": ["z"]})

    def test_apply_env_rules(self):
        config = {"db": "scalar", "a": {"b": 1}}
        apply_env(config, {"APP_DB__HOST": "x", "OTHER_A__B": "no", "APP_A__C": "3"})
        self.assertEqual(config, {"db": {"host": "x"}, "a": {"b": 1, "c": "3"}})
        self.assertEqual(apply_env({}, {"X_FOO": "1"}, prefix="X_"), {"foo": "1"})

    def test_env_applies_after_overrides(self):
        cfg = load_config({"db": {"host": "from-override"}}, env={"APP_DB__HOST": "from-env"})
        self.assertEqual(cfg["db"]["host"], "from-env")
        self.assertEqual(cfg["db"]["port"], 5432)


if __name__ == "__main__":
    unittest.main()
