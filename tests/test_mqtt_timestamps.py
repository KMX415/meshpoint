"""Reception timestamps must survive MQTT protobuf serialization."""

import json
import unittest
from datetime import datetime

from meshtastic.protobuf.mqtt_pb2 import ServiceEnvelope

from src.models.packet import Packet, PacketType, Protocol
from src.relay.mqtt_formatter import MeshtasticMqttFormatter


class TestMqttTimestamps(unittest.TestCase):
    def test_capture_time_survives_decoded_and_encrypted_output(self):
        formatter = MeshtasticMqttFormatter("msh", "US", "!12345678")
        # Equivalent instants in UTC and a local offset; fractional seconds
        # must become Unix seconds, not milliseconds or publish time.
        for capture_time in (
            "2026-10-02T00:31:33.084673+00:00",
            "2026-10-01T17:31:33.084673-07:00",
        ):
            for encrypted in (False, True):
                with self.subTest(capture_time=capture_time, encrypted=encrypted):
                    packet = Packet(
                        packet_id="000042ab",
                        source_id="12345678",
                        destination_id="ffffffff",
                        protocol=Protocol.MESHTASTIC,
                        packet_type=PacketType.TEXT,
                        timestamp=datetime.fromisoformat(capture_time),
                        decoded_payload=None if encrypted else {"text": "test"},
                        encrypted_payload=b"test ciphertext" if encrypted else None,
                    )
                    message = formatter.format(packet)
                    self.assertIsNotNone(message)
                    received = ServiceEnvelope.FromString(message.payload).packet
                    self.assertEqual(received.rx_time, 1790901093)
                    self.assertEqual(received.id, 0x42AB)
                    if encrypted:
                        self.assertEqual(received.encrypted, packet.encrypted_payload)
                    else:
                        self.assertEqual(received.decoded.payload, b"test")
                    json_message = formatter.format_json(packet)
                    self.assertEqual(
                        json.loads(json_message.payload)["timestamp"], received.rx_time
                    )
