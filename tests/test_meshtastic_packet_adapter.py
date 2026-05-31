"""Tests for meshtastic packet adapter."""

import unittest
from unittest.mock import MagicMock

from src.capture.meshtastic_packet_adapter import (
    _mesh_packet_to_lora_bytes,
    packet_dict_to_raw_capture,
)


class TestMeshtasticPacketAdapter(unittest.TestCase):
    def test_raw_hex_string_converted(self):
        packet = {
            "raw": "0102030405060708090a0b0c0d0e0f10",
            "rxRssi": -90,
            "rxSnr": 5.5,
        }
        raw = packet_dict_to_raw_capture(packet, "meshtasticd")
        self.assertIsNotNone(raw)
        self.assertEqual(raw.payload, bytes.fromhex("0102030405060708090a0b0c0d0e0f10"))
        self.assertIsNone(raw.meshtastic_api_packet)

    def test_mesh_packet_proto_with_encrypted_body(self):
        class FakeMeshPacket:
            def WhichOneof(self, _name: str) -> str:
                return "encrypted"

            encrypted = b"\xaa\xbb\xcc"
            to = 0xFFFFFFFF
            id = 42
            hop_limit = 3
            hop_start = 3
            want_ack = False
            via_mqtt = False
            channel = 8
            next_hop = 0
            relay_node = 0

        mp = FakeMeshPacket()
        setattr(mp, "from", 0x12345678)

        lora = _mesh_packet_to_lora_bytes(mp)
        self.assertIsNotNone(lora)
        self.assertEqual(len(lora), 16 + 3)

        raw = packet_dict_to_raw_capture(
            {"raw": mp, "rxRssi": -88, "rxSnr": 4.0},
            "meshtasticd",
        )
        self.assertIsNotNone(raw)
        self.assertEqual(raw.payload, lora)

    def test_decoded_api_packet_uses_side_channel(self):
        packet = {
            "raw": MagicMock(WhichOneof=MagicMock(return_value="decoded")),
            "from": 0xAABBCCDD,
            "to": 0xFFFFFFFF,
            "id": 99,
            "hopLimit": 3,
            "hopStart": 3,
            "decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "hello"},
            "rxRssi": -91,
            "rxSnr": 6.0,
        }
        raw = packet_dict_to_raw_capture(packet, "meshtasticd")
        self.assertIsNotNone(raw)
        self.assertEqual(raw.payload, b"")
        self.assertIs(raw.meshtastic_api_packet, packet)

    def test_meshtastic_python_decoded_payload_not_reencrypted(self):
        """Regression: decoded payload must not be wrapped as fake LoRa ciphertext."""
        packet = {
            "from": 0x9EA7E9D9,
            "to": 0xFFFFFFFF,
            "id": 12345,
            "hopLimit": 3,
            "hopStart": 3,
            "channel": 0,
            "decoded": {
                "portnum": "NODEINFO_APP",
                "payload": b"\x08\x01",
                "user": {
                    "longName": "Mesh Node",
                    "shortName": "MNOD",
                    "hwModel": "PORTDUINO",
                },
            },
            "raw": MagicMock(WhichOneof=MagicMock(return_value="decoded")),
        }
        raw = packet_dict_to_raw_capture(packet, "meshtasticd")
        self.assertIsNotNone(raw)
        self.assertIs(raw.meshtastic_api_packet, packet)
        self.assertEqual(raw.payload, b"")

    def test_empty_packet_returns_none(self):
        self.assertIsNone(packet_dict_to_raw_capture({}, "meshtasticd"))

    def test_unset_meshtasticd_rssi_snr_are_unknown(self):
        packet = {
            "from": 0x9EA7E9D9,
            "decoded": {"portnum": "TELEMETRY_APP"},
            "rxRssi": 0,
            "rxSnr": 0.0,
        }
        raw = packet_dict_to_raw_capture(packet, "meshtasticd")
        self.assertIsNotNone(raw)
        assert raw is not None
        self.assertIsNone(raw.signal.rssi)
        self.assertIsNone(raw.signal.snr)


if __name__ == "__main__":
    unittest.main()
