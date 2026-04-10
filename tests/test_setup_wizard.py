"""Tests for setup wizard helpers: config loading and float prompts."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from src.cli.setup_wizard import _load_existing_config


class TestLoadExistingConfig(unittest.TestCase):

    def test_returns_empty_dict_when_no_file(self):
        with patch.object(
            Path, "exists", return_value=False
        ):
            result = _load_existing_config()
            self.assertEqual(result, {})

    def test_loads_valid_yaml(self):
        data = {"device": {"device_name": "TestPoint"}, "radio": {"region": "US"}}
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump(data, f)
            tmp_path = f.name

        import src.cli.setup_wizard as sw
        original = sw.LOCAL_CONFIG_PATH
        try:
            sw.LOCAL_CONFIG_PATH = Path(tmp_path)
            result = _load_existing_config()
            self.assertEqual(result["device"]["device_name"], "TestPoint")
            self.assertEqual(result["radio"]["region"], "US")
        finally:
            sw.LOCAL_CONFIG_PATH = original
            Path(tmp_path).unlink(missing_ok=True)

    def test_returns_empty_for_non_dict_yaml(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write("just a string\n")
            tmp_path = f.name

        import src.cli.setup_wizard as sw
        original = sw.LOCAL_CONFIG_PATH
        try:
            sw.LOCAL_CONFIG_PATH = Path(tmp_path)
            result = _load_existing_config()
            self.assertEqual(result, {})
        finally:
            sw.LOCAL_CONFIG_PATH = original
            Path(tmp_path).unlink(missing_ok=True)

    def test_returns_empty_for_corrupt_yaml(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(": : : invalid yaml {{{\n")
            tmp_path = f.name

        import src.cli.setup_wizard as sw
        original = sw.LOCAL_CONFIG_PATH
        try:
            sw.LOCAL_CONFIG_PATH = Path(tmp_path)
            result = _load_existing_config()
            self.assertEqual(result, {})
        finally:
            sw.LOCAL_CONFIG_PATH = original
            Path(tmp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
