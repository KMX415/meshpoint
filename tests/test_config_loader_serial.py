"""Tests for multi-stick ``capture.serial`` config coercion.

Credit: javastraat/meshpoint ``deda84b``.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.config import (
    AppConfig,
    CaptureConfig,
    SerialDeviceConfig,
    _apply_yaml,
    _coerce_serial_devices,
)


class SerialDeviceConfigTest(unittest.TestCase):
    def _write(self, text: str) -> Path:
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        )
        tmp.write(text)
        tmp.close()
        path = Path(tmp.name)
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        return path

    def test_default_is_empty_list(self):
        cap = CaptureConfig()
        self.assertEqual(cap.serial, [])

    def test_serial_device_config_defaults(self):
        dev = SerialDeviceConfig()
        self.assertIsNone(dev.serial_port)
        self.assertEqual(dev.serial_baud, 115200)
        self.assertEqual(dev.label, "")

    def test_coerce_parses_list_of_dicts(self):
        devices = _coerce_serial_devices([
            {"serial_port": "/dev/ttyUSB0", "label": "433"},
            {"serial_port": "/dev/ttyUSB1", "label": "868", "serial_baud": 57600},
        ])
        self.assertEqual(len(devices), 2)
        self.assertEqual(devices[0].serial_port, "/dev/ttyUSB0")
        self.assertEqual(devices[0].label, "433")
        self.assertEqual(devices[0].serial_baud, 115200)
        self.assertEqual(devices[1].serial_baud, 57600)

    def test_coerce_ignores_non_list_value(self):
        self.assertEqual(
            _coerce_serial_devices({"serial_port": "/dev/ttyUSB0"}), [],
        )
        self.assertEqual(_coerce_serial_devices(None), [])

    def test_apply_yaml_populates_serial_list(self):
        cfg = AppConfig()
        path = self._write(
            "capture:\n"
            "  serial:\n"
            "    - serial_port: /dev/ttyUSB0\n"
            "      label: \"433\"\n"
            "    - serial_port: /dev/ttyUSB1\n"
            "      label: \"868\"\n"
        )
        with self.assertNoLogs("src.config", level="WARNING"):
            _apply_yaml(cfg, path)
        self.assertEqual(len(cfg.capture.serial), 2)
        self.assertEqual(cfg.capture.serial[0].label, "433")
        self.assertEqual(cfg.capture.serial[1].serial_port, "/dev/ttyUSB1")

    def test_legacy_scalar_config_unaffected(self):
        cfg = AppConfig()
        path = self._write(
            "capture:\n"
            "  serial_port: /dev/ttyUSB0\n"
            "  serial_baud: 115200\n"
        )
        _apply_yaml(cfg, path)
        self.assertEqual(cfg.capture.serial, [])
        self.assertEqual(cfg.capture.serial_port, "/dev/ttyUSB0")


if __name__ == "__main__":
    unittest.main()
