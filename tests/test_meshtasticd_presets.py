"""Bundled meshtasticd LoRa presets for WisMesh Node installs."""

from pathlib import Path
import unittest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_PRESET_DIR = _REPO_ROOT / "config" / "meshtasticd"


class TestMeshtasticdBundledPresets(unittest.TestCase):
    def test_13302_default_preset_has_pa_config(self) -> None:
        path = _PRESET_DIR / "lora-RAK6421-13302-slot1.yaml"
        text = path.read_text(encoding="utf-8")
        self.assertIn("Enable_Pins:", text)
        self.assertIn("TX_GAIN_LORA:", text)
        self.assertIn("CS: 8", text)

    def test_13300_override_preset_has_no_tx_gain(self) -> None:
        path = _PRESET_DIR / "lora-RAK6421-13300-slot1.yaml"
        text = path.read_text(encoding="utf-8")
        self.assertIn("Enable_Pins:", text)
        self.assertNotIn("TX_GAIN_LORA:", text)

    def test_config_default_matches_13302(self) -> None:
        from src.config import MeshtasticdConfig

        self.assertEqual(
            MeshtasticdConfig().preset,
            "lora-RAK6421-13302-slot1.yaml",
        )
