"""Tests for WisBlock module preset install helpers."""

import unittest
from pathlib import Path
from unittest.mock import patch

from src.capture.meshtasticd_module_preset import (
    MODULE_CATALOG,
    install_preset_file,
    list_module_presets,
    persist_preset_to_yaml,
    resolve_module_preset,
)


class TestModuleCatalog(unittest.TestCase):
    def test_list_marks_active(self):
        active = "lora-RAK6421-13302-slot1.yaml"
        presets = list_module_presets(active)
        self.assertEqual(len(presets), len(MODULE_CATALOG))
        active_rows = [p for p in presets if p["active"]]
        self.assertEqual(len(active_rows), 1)
        self.assertEqual(active_rows[0]["module_id"], "13302")

    def test_resolve_unknown_raises(self):
        with self.assertRaises(ValueError):
            resolve_module_preset("9999")


class TestInstallPresetFile(unittest.TestCase):
    def test_install_copies_and_removes_sibling(self):
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundled = root / "config" / "meshtasticd"
            bundled.mkdir(parents=True)
            src_13302 = bundled / "lora-RAK6421-13302-slot1.yaml"
            src_13302.write_text("  # CS: 8\n", encoding="utf-8")

            configd = root / "config.d"
            configd.mkdir()
            stale = configd / "lora-RAK6421-13300-slot1.yaml"
            stale.write_text("old", encoding="utf-8")

            with patch(
                "src.capture.meshtasticd_module_preset.MESHTASTICD_CONFIGD",
                configd,
            ), patch(
                "src.capture.meshtasticd_module_preset.MESHTASTICD_AVAILABLE",
                root / "missing_available",
            ), patch(
                "src.capture.meshtasticd_module_preset.meshpoint_root",
                return_value=root,
            ):
                install_preset_file("lora-RAK6421-13302-slot1.yaml", root=root)

            target = configd / "lora-RAK6421-13302-slot1.yaml"
            self.assertTrue(target.is_file())
            self.assertIn("CS: 8", target.read_text(encoding="utf-8"))
            self.assertFalse(stale.exists())


class TestPersistYaml(unittest.TestCase):
    def test_merges_nested_meshtasticd(self):
        import tempfile
        import yaml

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "local.yaml"
            path.write_text(
                "capture:\n  meshtasticd:\n    host: 127.0.0.1\n    port: 4403\n",
                encoding="utf-8",
            )
            with patch("src.config._get_local_yaml_path", return_value=path):
                persist_preset_to_yaml("lora-RAK6421-13300-slot1.yaml")

            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            md = data["capture"]["meshtasticd"]
            self.assertEqual(md["host"], "127.0.0.1")
            self.assertEqual(md["preset"], "lora-RAK6421-13300-slot1.yaml")


if __name__ == "__main__":
    unittest.main()
