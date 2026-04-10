"""Tests for TxService helpers: preset names and destination resolution."""

from __future__ import annotations

import unittest

from src.models.packet import Protocol
from src.transmit.tx_service import (
    BROADCAST_ADDR_MC,
    BROADCAST_ADDR_MT,
    PRESET_DISPLAY_NAMES,
    TxService,
)


class TestPresetDisplayNames(unittest.TestCase):

    def test_longfast(self):
        self.assertEqual(PRESET_DISPLAY_NAMES[(11, 250)], "LongFast")

    def test_shortfast(self):
        self.assertEqual(PRESET_DISPLAY_NAMES[(7, 250)], "ShortFast")

    def test_shortturbo(self):
        self.assertEqual(PRESET_DISPLAY_NAMES[(7, 500)], "ShortTurbo")

    def test_mediumfast(self):
        self.assertEqual(PRESET_DISPLAY_NAMES[(9, 250)], "MediumFast")

    def test_all_presets_present(self):
        expected = {
            "ShortFast", "ShortTurbo", "ShortSlow",
            "MediumFast", "MediumSlow",
            "LongFast", "LongMod", "LongSlow", "VLongSlow",
        }
        self.assertEqual(set(PRESET_DISPLAY_NAMES.values()), expected)

    def test_custom_falls_through(self):
        self.assertNotIn((6, 125), PRESET_DISPLAY_NAMES)


class TestResolveDestination(unittest.TestCase):

    def test_broadcast_string(self):
        result = TxService._resolve_destination("broadcast", Protocol.MESHTASTIC)
        self.assertEqual(result, BROADCAST_ADDR_MT)

    def test_broadcast_all(self):
        result = TxService._resolve_destination("all", Protocol.MESHTASTIC)
        self.assertEqual(result, BROADCAST_ADDR_MT)

    def test_broadcast_hex_ff(self):
        result = TxService._resolve_destination("ffffffff", Protocol.MESHTASTIC)
        self.assertEqual(result, BROADCAST_ADDR_MT)

    def test_non_numeric_string_falls_to_broadcast(self):
        result = TxService._resolve_destination("deadbeef", Protocol.MESHTASTIC)
        self.assertEqual(result, BROADCAST_ADDR_MT)

    def test_numeric_string_parsed_as_int(self):
        result = TxService._resolve_destination("12345678", Protocol.MESHTASTIC)
        self.assertEqual(result, 12345678)

    def test_integer_passthrough(self):
        result = TxService._resolve_destination(0x12345678, Protocol.MESHTASTIC)
        self.assertEqual(result, 0x12345678)

    def test_broadcast_constants(self):
        self.assertEqual(BROADCAST_ADDR_MT, 0xFFFFFFFF)
        self.assertEqual(BROADCAST_ADDR_MC, 0xFFFF)


if __name__ == "__main__":
    unittest.main()
