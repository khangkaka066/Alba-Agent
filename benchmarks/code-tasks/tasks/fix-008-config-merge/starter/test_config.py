import unittest

from config import load_config


class ConfigTests(unittest.TestCase):
    def test_defaults_not_polluted(self):
        cfg = load_config()
        cfg["logging"]["handlers"].append("file")
        self.assertEqual(load_config()["logging"]["handlers"], ["console"])

    def test_overrides_not_aliased(self):
        overrides = {"logging": {"handlers": ["syslog"]}}
        cfg = load_config(overrides)
        overrides["logging"]["handlers"].append("late")
        self.assertEqual(cfg["logging"]["handlers"], ["syslog"])


if __name__ == "__main__":
    unittest.main()
