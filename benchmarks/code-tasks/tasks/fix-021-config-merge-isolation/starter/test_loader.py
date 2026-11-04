import unittest

from loader import DEFAULTS, load_config


class LoaderTests(unittest.TestCase):
    def test_overrides_are_merged(self):
        config = load_config({"db": {"host": "db.internal"}, "cache": {"ttl": 5}})
        self.assertEqual(config["db"]["host"], "db.internal")
        self.assertEqual(config["db"]["port"], 5432)
        self.assertEqual(config["cache"]["ttl"], 5)

    def test_env_does_not_leak_into_later_loads(self):
        first = load_config(env={"APP_DB__OPTIONS__SSL": "true"})
        self.assertEqual(first["db"]["options"]["ssl"], "true")
        second = load_config()
        self.assertIs(second["db"]["options"]["ssl"], False)
        self.assertIs(DEFAULTS["db"]["options"]["ssl"], False)

    def test_mutating_a_result_does_not_change_the_next(self):
        first = load_config()
        first["features"].append("export")
        self.assertEqual(load_config()["features"], ["search"])


if __name__ == "__main__":
    unittest.main()
