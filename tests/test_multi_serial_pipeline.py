"""Multi-serial source wiring tests.

Credit: javastraat/meshpoint ``deda84b``.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.api.server import _add_serial_source
from src.config import AppConfig, SerialDeviceConfig


class AddSerialSourceTest(unittest.TestCase):
    def test_legacy_scalars_add_one_unlabelled_source(self):
        config = AppConfig()
        config.capture.serial_port = "/dev/ttyUSB0"
        config.capture.serial = []
        coord = MagicMock()
        coord.capture_coordinator = MagicMock()

        with patch("src.capture.serial_source.SerialCaptureSource") as cls:
            instance = MagicMock()
            instance.name = "serial"
            cls.return_value = instance
            _add_serial_source(coord, config)

        cls.assert_called_once_with(
            port="/dev/ttyUSB0", baud=115200, label=""
        )
        coord.capture_coordinator.add_source.assert_called_once_with(instance)

    def test_serial_list_adds_labelled_sources(self):
        config = AppConfig()
        config.capture.serial = [
            SerialDeviceConfig(serial_port="/dev/ttyUSB0", label="433"),
            SerialDeviceConfig(serial_port="/dev/ttyUSB1", label="868"),
        ]
        coord = MagicMock()
        coord.capture_coordinator = MagicMock()

        with patch("src.capture.serial_source.SerialCaptureSource") as cls:
            a = MagicMock()
            a.name = "serial_433"
            b = MagicMock()
            b.name = "serial_868"
            cls.side_effect = [a, b]
            _add_serial_source(coord, config)

        self.assertEqual(cls.call_count, 2)
        cls.assert_any_call(port="/dev/ttyUSB0", baud=115200, label="433")
        cls.assert_any_call(port="/dev/ttyUSB1", baud=115200, label="868")
        self.assertEqual(coord.capture_coordinator.add_source.call_count, 2)


if __name__ == "__main__":
    unittest.main()
