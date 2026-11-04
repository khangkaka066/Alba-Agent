import unittest

import config
from config import get_path, load_config, merge


class ConfigFullTests(unittest.TestCase):
    def test_defaults_not_polluted_by_nested_list(self):
        cfg = load_config()
        cfg["logging"]["handlers"].append("file")
        self.assertEqual(load_config()["logging"]["handlers"], ["console"])
        self.assertEqual(config.DEFAULTS["logging"]["handlers"], ["console"])

    def test_defaults_not_polluted_by_nested_dict(self):
        cfg = load_config({"debug": True})
        cfg["server"]["port"] = 1
        self.assertEqual(config.DEFAULTS["server"]["port"], 8080)
        self.assertEqual(load_config()["server"]["port"], 8080)

    def test_overrides_not_aliased(self):
        overrides = {"logging": {"handlers": ["syslog"]}, "extra": {"k": [1]}}
        cfg = load_config(overrides)
        overrides["logging"]["handlers"].append("late")
        overrides["extra"]["k"].append(2)
        self.assertEqual(cfg["logging"]["handlers"], ["syslog"])
        self.assertEqual(cfg["extra"], {"k": [1]})

    def test_recursive_merge(self):
        cfg = load_config({"server": {"port": 9000}, "debug": True})
        self.assertEqual(cfg["server"], {"host": "localhost", "port": 9000})
        self.assertTrue(cfg["debug"])
        self.assertEqual(cfg["logging"]["level"], "INFO")

    def test_non_dict_replaces(self):
        cfg = merge({"a": {"b": 1}}, {"a": 5})
        self.assertEqual(cfg, {"a": 5})
        cfg = merge({"a": 5}, {"a": {"b": 1}})
        self.assertEqual(cfg, {"a": {"b": 1}})

    def test_inputs_not_modified(self):
        base = {"a": {"b": [1]}}
        over = {"a": {"c": 2}}
        merge(base, over)
        self.assertEqual(base, {"a": {"b": [1]}})
        self.assertEqual(over, {"a": {"c": 2}})

    def test_result_shares_nothing_with_base(self):
        base = {"a": {"b": [1]}, "z": [0]}
        result = merge(base, {"y": 1})
        result["a"]["b"].append(2)
        result["z"].append(1)
        self.assertEqual(base, {"a": {"b": [1]}, "z": [0]})

    def test_repeated_loads_independent(self):
        first = load_config()
        second = load_config()
        first["server"]["host"] = "example"
        self.assertEqual(second["server"]["host"], "localhost")

    def test_get_path(self):
        cfg = load_config()
        self.assertEqual(get_path(cfg, "server.port"), 8080)
        self.assertIsNone(get_path(cfg, "server.nope"))
        self.assertEqual(get_path(cfg, "a.b.c", "dflt"), "dflt")


if __name__ == "__main__":
    unittest.main()
