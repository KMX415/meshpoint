"""Tests for the two-layer YAML config loader in ``src.config``.

Focuses on the merge path and the unknown-key warning: a typo in
``local.yaml`` (``tx_powr_dbm`` for ``tx_power_dbm``, a misspelled
section name, a stray nested key) is silently dropped by the
dataclass merge, so the loader now logs a single warning listing the
ignored keys to help operators debug "my setting did nothing".
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from src.config import (
    AppConfig,
    _apply_yaml,
    _collect_unknown_keys,
    load_config,
)


class CollectUnknownKeysTest(unittest.TestCase):
    def test_flat_unknown_key_is_reported(self):
        cfg = AppConfig()
        unknown = _collect_unknown_keys(
            cfg.transmit, {"tx_power_dbm": 20, "tx_powr_dbm": 99}
        )
        self.assertEqual(unknown, ["tx_powr_dbm"])

    def test_all_known_keys_report_nothing(self):
        cfg = AppConfig()
        unknown = _collect_unknown_keys(
            cfg.transmit, {"enabled": True, "tx_power_dbm": 20, "hop_limit": 5}
        )
        self.assertEqual(unknown, [])

    def test_nested_dataclass_is_recursed_with_dotted_path(self):
        cfg = AppConfig()
        unknown = _collect_unknown_keys(
            cfg.transmit,
            {"nodeinfo": {"interval_minutes": 60, "intrval_minutes": 60}},
        )
        self.assertEqual(unknown, ["nodeinfo.intrval_minutes"])

    def test_mapping_field_values_are_not_scanned(self):
        # meshtastic.channel_keys is a user-populated dict[str, str]; its
        # arbitrary channel names must not be flagged as unknown keys.
        cfg = AppConfig()
        unknown = _collect_unknown_keys(
            cfg.meshtastic,
            {"channel_keys": {"Secret": "AbCd==", "AnotherChan": "EfGh=="}},
        )
        self.assertEqual(unknown, [])


class ApplyYamlUnknownKeyTest(unittest.TestCase):
    def _write(self, text: str) -> Path:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        )
        tmp.write(text)
        tmp.close()
        path = Path(tmp.name)
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        return path

    def test_unknown_key_not_applied_and_warns(self):
        cfg = AppConfig()
        path = self._write(
            "transmit:\n"
            "  tx_power_dbm: 20\n"
            "  tx_powr_dbm: 99\n"
        )
        with self.assertLogs("src.config", level="WARNING") as captured:
            _apply_yaml(cfg, path)

        # Valid key applied; typo dropped (stays at the dataclass default).
        self.assertEqual(cfg.transmit.tx_power_dbm, 20)
        self.assertFalse(hasattr(cfg.transmit, "tx_powr_dbm"))
        joined = "\n".join(captured.output)
        self.assertIn("transmit.tx_powr_dbm", joined)
        self.assertIn(str(path), joined)

    def test_unknown_top_level_section_is_reported(self):
        cfg = AppConfig()
        path = self._write("transmt:\n  enabled: true\n")
        with self.assertLogs("src.config", level="WARNING") as captured:
            _apply_yaml(cfg, path)
        # The whole misspelled section is ignored, not silently swallowed.
        self.assertFalse(cfg.transmit.enabled)
        self.assertIn("transmt", "\n".join(captured.output))

    def test_non_mapping_top_level_is_ignored_not_crashed(self):
        cfg = AppConfig()
        path = self._write("- just\n- a\n- list\n")
        with self.assertLogs("src.config", level="WARNING"):
            _apply_yaml(cfg, path)  # must not raise
        # Defaults left intact.
        self.assertEqual(cfg.radio.region, "US")

    def test_clean_config_emits_no_warning(self):
        cfg = AppConfig()
        path = self._write(
            "radio:\n"
            "  region: EU_868\n"
            "transmit:\n"
            "  enabled: true\n"
            "  nodeinfo:\n"
            "    interval_minutes: 60\n"
        )
        with self.assertNoLogs("src.config", level="WARNING"):
            _apply_yaml(cfg, path)

        self.assertEqual(cfg.radio.region, "EU_868")
        self.assertTrue(cfg.transmit.enabled)
        self.assertEqual(cfg.transmit.nodeinfo.interval_minutes, 60)


class LoadConfigIntegrationTest(unittest.TestCase):
    def test_typo_in_local_yaml_is_warned_and_ignored(self):
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        )
        tmp.write("transmit:\n  hop_limit: 7\n  hoplimit: 99\n")
        tmp.close()
        path = Path(tmp.name)
        self.addCleanup(lambda: path.unlink(missing_ok=True))

        old = os.environ.get("CONCENTRATOR_CONFIG")
        os.environ["CONCENTRATOR_CONFIG"] = str(path)
        try:
            with self.assertLogs("src.config", level="WARNING") as captured:
                cfg = load_config()
        finally:
            if old is None:
                os.environ.pop("CONCENTRATOR_CONFIG", None)
            else:
                os.environ["CONCENTRATOR_CONFIG"] = old

        self.assertEqual(cfg.transmit.hop_limit, 7)
        self.assertIn("transmit.hoplimit", "\n".join(captured.output))


if __name__ == "__main__":
    unittest.main()
