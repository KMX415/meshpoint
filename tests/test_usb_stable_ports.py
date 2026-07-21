"""Stable USB serial path enumeration helpers.

Credit: javastraat/meshpoint ``d6adb1e``.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from src.hal.usb_classifier import (
    PortClass,
    PortInfo,
    StablePortInfo,
    list_serial_ports_with_stable_paths,
)


class ListSerialPortsStablePathsTest(unittest.TestCase):
    @patch("src.hal.usb_classifier._resolve_symlinks")
    @patch("src.hal.usb_classifier.UsbPortClassifier.list_ports")
    def test_prefers_by_path_over_by_id(self, list_ports, resolve):
        list_ports.return_value = [
            PortInfo(
                device="/dev/ttyUSB0",
                vid=0x10C4,
                pid=0xEA60,
                manufacturer="Silicon Labs",
                product="CP210x",
                port_class=PortClass.UNKNOWN,
            )
        ]

        def _resolve(directory):
            name = str(directory)
            if name.endswith("by-path"):
                return {"/dev/ttyUSB0": "/dev/serial/by-path/platform-usb-0"}
            if name.endswith("by-id"):
                return {"/dev/ttyUSB0": "/dev/serial/by-id/usb-Silicon_Labs"}
            return {}

        resolve.side_effect = _resolve

        with patch("src.hal.usb_classifier.os.path.realpath", side_effect=lambda p: p):
            ports = list_serial_ports_with_stable_paths()

        self.assertEqual(len(ports), 1)
        self.assertIsInstance(ports[0], StablePortInfo)
        self.assertEqual(
            ports[0].stable_path, "/dev/serial/by-path/platform-usb-0"
        )


if __name__ == "__main__":
    unittest.main()
