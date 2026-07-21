"""Tests for MeshtasticDecoder.decode()'s pre_decoded fast path.

Covers packets a serial-connected Meshtastic USB stick already
decrypted locally (protobuf oneof discards ciphertext).
"""

from __future__ import annotations

import unittest

from meshtastic.protobuf import portnums_pb2, telemetry_pb2

from src.decode.crypto_service import CryptoService
from src.decode.meshtastic_decoder import MeshtasticDecoder
from src.models.packet import PacketType


def _header_only_frame(
    dest=0xFFFFFFFF,
    source=0x09D406F4,
    packet_id=555,
    hop_limit=3,
    hop_start=3,
    channel=0,
) -> bytes:
    import struct

    flags = (hop_limit & 0x07) | ((hop_start & 0x07) << 5)
    return struct.pack("<III", dest, source, packet_id) + bytes(
        [flags, channel, 0, 0]
    )


class MeshtasticDecoderPreDecodedTest(unittest.TestCase):
    def setUp(self):
        self.decoder = MeshtasticDecoder(CryptoService())

    def test_telemetry_portnum_yields_typed_packet_not_unknown(self):
        tel = telemetry_pb2.Telemetry()
        tel.device_metrics.battery_level = 87
        tel.device_metrics.voltage = 4.1
        pre_decoded = {
            "portnum": portnums_pb2.PortNum.TELEMETRY_APP,
            "payload": tel.SerializeToString(),
            "request_id": 0,
        }

        packet = self.decoder.decode(
            _header_only_frame(), pre_decoded=pre_decoded
        )

        self.assertIsNotNone(packet)
        self.assertEqual(packet.packet_type, PacketType.TELEMETRY)
        self.assertTrue(packet.decrypted)
        self.assertIsNone(packet.encrypted_payload)
        self.assertEqual(packet.decoded_payload["battery_level"], 87)
        self.assertAlmostEqual(packet.decoded_payload["voltage"], 4.1, places=2)

    def test_source_and_header_fields_come_from_the_frame(self):
        pre_decoded = {
            "portnum": portnums_pb2.PortNum.TELEMETRY_APP,
            "payload": telemetry_pb2.Telemetry().SerializeToString(),
        }
        packet = self.decoder.decode(
            _header_only_frame(source=0x09D406F4, hop_limit=3, hop_start=3),
            pre_decoded=pre_decoded,
        )
        self.assertEqual(packet.source_id, "09d406f4")
        self.assertEqual(packet.hop_count, 0)

    def test_request_id_is_attached_to_decoded_payload(self):
        pre_decoded = {
            "portnum": portnums_pb2.PortNum.TELEMETRY_APP,
            "payload": telemetry_pb2.Telemetry().SerializeToString(),
            "request_id": 99,
        }
        packet = self.decoder.decode(
            _header_only_frame(), pre_decoded=pre_decoded
        )
        self.assertEqual(packet.decoded_payload.get("request_id"), 99)

    def test_empty_payload_falls_back_to_unknown_not_encrypted(self):
        pre_decoded = {"portnum": -1, "payload": b""}

        packet = self.decoder.decode(
            _header_only_frame(), pre_decoded=pre_decoded
        )

        self.assertIsNotNone(packet)
        self.assertNotEqual(packet.packet_type, PacketType.ENCRYPTED)

    def test_too_short_frame_returns_none_even_with_pre_decoded(self):
        pre_decoded = {
            "portnum": portnums_pb2.PortNum.TELEMETRY_APP,
            "payload": b"",
        }
        self.assertIsNone(
            self.decoder.decode(b"\x00" * 4, pre_decoded=pre_decoded)
        )


if __name__ == "__main__":
    unittest.main()
