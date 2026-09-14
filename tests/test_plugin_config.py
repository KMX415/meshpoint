"""Optional configuration merges without changing core defaults."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import yaml
from src.config import AppConfig, _apply_yaml, save_section_to_yaml


class TestPluginConfig(unittest.TestCase):
    def test_save_download_permission_preserves_other_settings_and_reloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "local.yaml"
            path.write_text("plugins:\n  sample:\n    enabled: true\ndashboard:\n  title: Keep me\n", encoding="utf-8")
            with patch("src.config._get_local_yaml_path", return_value=path):
                for enabled in [True, False]:
                    save_section_to_yaml("plugin_sources_enabled", enabled)
                    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
                    self.assertIs(saved["plugin_sources_enabled"], enabled)
                    self.assertEqual(saved["dashboard"]["title"], "Keep me")
                    self.assertTrue(saved["plugins"]["sample"]["enabled"])
                    config = AppConfig()
                    _apply_yaml(config, path)
                    self.assertIs(config.plugin_sources_enabled, enabled)

    def test_device_permissions_require_explicit_yaml_boolean(self):
        self.assertFalse(AppConfig().plugin_sources_enabled)
        self.assertFalse(AppConfig().dashboard.web_terminal_enabled)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.yaml"
            for value, expected in [("true", True), ("false", False), ('"true"', False), ('"false"', False), ("1", False), ("null", False)]:
                with self.subTest(value=value):
                    config = AppConfig(plugin_sources_enabled=True)
                    config.dashboard.web_terminal_enabled = True
                    path.write_text(f"plugin_sources_enabled: {value}\ndashboard:\n  web_terminal_enabled: {value}\n", encoding="utf-8")
                    _apply_yaml(config, path)
                    self.assertIs(config.plugin_sources_enabled, expected)
                    self.assertIs(config.dashboard.web_terminal_enabled, expected)

    def test_missing_plugins_remain_empty(self):
        self.assertEqual(AppConfig().plugins, {})

    def test_layered_plugin_options_merge(self):
        config = AppConfig()
        config.plugins = {"sample": {"enabled": False, "existing": 1}}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.yaml"
            path.write_text("plugins:\n  sample:\n    enabled: true\n    option: two\n", encoding="utf-8")
            _apply_yaml(config, path)
        self.assertEqual(config.plugins["sample"], {"enabled": True, "existing": 1, "option": "two"})
        self.assertEqual(config.capture, AppConfig().capture)


if __name__ == "__main__":
    unittest.main()
