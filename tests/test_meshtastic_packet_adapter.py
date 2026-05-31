"""Tests for meshtastic packet adapter."""

import unittest

from src.capture.meshtastic_packet_adapter import packet_dict_to_raw_capture


class TestMeshtasticPacketAdapter(unittest.TestCase):
    def test_raw_hex_string_converted(self):
        packet = {
            "raw": "0102030405",
            "rxRssi": -90,
            "rxSnr": 5.5,
        }
        raw = packet_dict_to_raw_capture(packet, "meshtasticd")
        self.assertIsNotNone(raw)
        self.assertEqual(raw.payload, bytes.fromhex("0102030405"))
        self.assertEqual(raw.capture_source, "meshtasticd")
        self.assertEqual(raw.signal.rssi, -90.0)

    def test_reconstruct_from_decoded_when_raw_missing(self):
        packet = {
            "to": 0xFFFFFFFF,
            "from": 0x12345678,
            "id": 42,
            "hopLimit": 3,
            "hopStart": 3,
            "channel": 0,
            "decoded": {"portnum": 1},
        }
        raw = packet_dict_to_raw_capture(packet, "serial")
        self.assertIsNotNone(raw)
        self.assertGreaterEqual(len(raw.payload), 16)

    def test_empty_packet_returns_none(self):
        self.assertIsNone(packet_dict_to_raw_capture({}, "meshtasticd"))


if __name__ == "__main__":
    unittest.main()
