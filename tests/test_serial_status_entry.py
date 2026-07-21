"""Serial status entry + source discovery helpers.

Credit: javastraat/meshpoint ``77cdaa2``.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from src.api.routes.config_routes import _serial_status_entry
from src.api.server import _find_serial_sources
from src.capture.serial_source import SerialCaptureSource


class SerialStatusEntryTest(unittest.TestCase):
    def test_includes_name_connected_freq_and_own_id(self):
        src = MagicMock()
        src.name = "serial_433"
        src.connected = True
        src.get_radio_info.return_value = {
            "region": "EU_868",
            "channel_num": 0,
            "bandwidth_khz": 250.0,
            "channel_name": "",
            "modem_preset": "LONG_FAST",
            "use_preset": True,
            "frequency_offset": 0.0,
            "override_frequency": 0.0,
            "own_node_num": 0xAABBCCDD,
        }
        entry = _serial_status_entry(src)
        self.assertEqual(entry["name"], "serial_433")
        self.assertTrue(entry["connected"])
        self.assertEqual(entry["frequency_mhz"], 869.525)
        self.assertEqual(entry["own_node_id_hex"], "aabbccdd")


class FindSerialSourcesTest(unittest.TestCase):
    def test_returns_only_serial_capture_sources(self):
        serial = SerialCaptureSource(port="/dev/ttyUSB0", label="433")
        other = MagicMock()
        other.name = "concentrator"
        coord = MagicMock()
        coord.capture_coordinator._sources = [other, serial]
        found = _find_serial_sources(coord)
        self.assertEqual(found, [serial])


if __name__ == "__main__":
    unittest.main()
