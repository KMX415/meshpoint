"""Tests for ``LocationConfig``: defaults, YAML merge, and validation seams."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.config import (
    AppConfig,
    LocationConfig,
    _apply_yaml,
    _merge_dataclass,
)


class TestLocationConfigDefaults(unittest.TestCase):
    """Out-of-the-box defaults match the v0.7.5 plan."""

    def test_default_source_is_static(self) -> None:
        cfg = LocationConfig()
        self.assertEqual(cfg.source, "static")

    def test_default_gpsd_host_is_localhost(self) -> None:
        cfg = LocationConfig()
        self.assertEqual(cfg.gpsd_host, "127.0.0.1")

    def test_default_gpsd_port_is_well_known(self) -> None:
        cfg = LocationConfig()
        self.assertEqual(cfg.gpsd_port, 2947)

    def test_default_update_interval_is_five_seconds(self) -> None:
        cfg = LocationConfig()
        self.assertEqual(cfg.update_interval_seconds, 5)

    def test_default_min_fix_quality_is_2d(self) -> None:
        # 0=any incl. no-fix, 1=2D, 2=3D. Default 1 keeps the dashboard
        # from moving on a no-fix TPV.
        cfg = LocationConfig()
        self.assertEqual(cfg.min_fix_quality, 1)


class TestAppConfigComposition(unittest.TestCase):
    """``AppConfig`` exposes ``location`` as a first-class section."""

    def test_app_config_has_location_field(self) -> None:
        app = AppConfig()
        self.assertIsInstance(app.location, LocationConfig)

    def test_independent_instances_per_app_config(self) -> None:
        a = AppConfig()
        b = AppConfig()
        a.location.source = "gpsd"
        # Per ``field(default_factory=...)`` semantics, each AppConfig
        # gets its own LocationConfig instance.
        self.assertEqual(b.location.source, "static")


class TestLocationYamlMerge(unittest.TestCase):
    """YAML overrides apply through ``_apply_yaml`` like every other section."""

    def _write_yaml(self, body: str) -> Path:
        path = Path(tempfile.NamedTemporaryFile(suffix=".yaml", delete=False).name)
        path.write_text(body)
        return path

    def test_partial_override_preserves_other_fields(self) -> None:
        path = self._write_yaml(
            "location:\n"
            "  source: gpsd\n"
            "  gpsd_host: 192.168.0.50\n"
        )
        try:
            cfg = AppConfig()
            _apply_yaml(cfg, path)

            self.assertEqual(cfg.location.source, "gpsd")
            self.assertEqual(cfg.location.gpsd_host, "192.168.0.50")
            # Untouched fields keep defaults.
            self.assertEqual(cfg.location.gpsd_port, 2947)
            self.assertEqual(cfg.location.update_interval_seconds, 5)
            self.assertEqual(cfg.location.min_fix_quality, 1)
        finally:
            path.unlink()

    def test_uart_source_round_trips(self) -> None:
        path = self._write_yaml("location:\n  source: uart\n")
        try:
            cfg = AppConfig()
            _apply_yaml(cfg, path)
            self.assertEqual(cfg.location.source, "uart")
        finally:
            path.unlink()

    def test_remote_gpsd_round_trips(self) -> None:
        path = self._write_yaml(
            "location:\n"
            "  source: gpsd\n"
            "  gpsd_host: gps.lan\n"
            "  gpsd_port: 2948\n"
            "  update_interval_seconds: 10\n"
            "  min_fix_quality: 2\n"
        )
        try:
            cfg = AppConfig()
            _apply_yaml(cfg, path)

            self.assertEqual(cfg.location.gpsd_host, "gps.lan")
            self.assertEqual(cfg.location.gpsd_port, 2948)
            self.assertEqual(cfg.location.update_interval_seconds, 10)
            self.assertEqual(cfg.location.min_fix_quality, 2)
        finally:
            path.unlink()

    def test_unknown_keys_are_ignored(self) -> None:
        # ``_merge_dataclass`` silently skips fields that aren't on the
        # dataclass: forward-compat for older Meshpoints reading newer
        # local.yaml after a downgrade.
        cfg = LocationConfig()
        _merge_dataclass(cfg, {"source": "gpsd", "future_field": True})
        self.assertEqual(cfg.source, "gpsd")
        self.assertFalse(hasattr(cfg, "future_field"))


if __name__ == "__main__":
    unittest.main()
