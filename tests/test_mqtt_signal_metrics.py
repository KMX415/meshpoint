"""Optional signal metrics survive MQTT formatting independently."""

import json
import unittest
from datetime import datetime, timezone

from meshtastic.protobuf.mqtt_pb2 import ServiceEnvelope

from src.models.packet import Packet, PacketType, Protocol
from src.models.signal import SignalMetrics
from src.relay.mqtt_formatter import MeshCoreMqttFormatter, MeshtasticMqttFormatter


class TestMqttSignalMetrics(unittest.TestCase):
    # Explicit expectations protect both partial directions and valid zero SNR.
    CASES = (
        ("rssi_only", -105, None, {"rssi": -105}),
        ("snr_only", None, 7.5, {"snr": 7.5}),
        ("neither", None, None, {}),
        ("both", -105, 7.5, {"rssi": -105, "snr": 7.5}),
        ("zero_snr", -105, 0.0, {"rssi": -105, "snr": 0.0}),
        ("no_signal", None, None, {}),
    )

    def make_packet(self, protocol, name, rssi, snr):
        return Packet(
            packet_id="000042ab",
            source_id="12345678",
            destination_id="ffffffff",
            protocol=protocol,
            packet_type=PacketType.TEXT,
            timestamp=datetime(2026, 10, 9, tzinfo=timezone.utc),
            decoded_payload={"text": "signal regression"},
            signal=None if name == "no_signal" else SignalMetrics(
                frequency_mhz=915.0, spreading_factor=7, bandwidth_khz=250.0,
                rssi=rssi, snr=snr,
            ),
        )

    def test_decoded_protobuf_preserves_available_metrics(self):
        formatter = MeshtasticMqttFormatter("msh", "US", "!12345678")
        for name, rssi, snr, expected in self.CASES:
            with self.subTest(case=name):
                packet = self.make_packet(Protocol.MESHTASTIC, name, rssi, snr)
                message = formatter.format(packet)
                self.assertIsNotNone(message)
                received = ServiceEnvelope.FromString(message.payload).packet
                self.assertEqual(received.decoded.payload, b"signal regression")
                self.assertEqual(received.rx_rssi, expected.get("rssi", 0))
                self.assertEqual(received.rx_snr, expected.get("snr", 0.0))
                # These proto3 scalars omit defaults on the wire. Zero SNR
                # therefore has no distinct presence bit; JSON checks it below.
                fields = {field.name for field, _ in received.ListFields()}
                self.assertEqual("rx_rssi" in fields, "rssi" in expected)
                self.assertEqual("rx_snr" in fields, expected.get("snr", 0) != 0)

    def assert_json_metrics(self, formatter, protocol):
        for name, rssi, snr, expected in self.CASES:
            with self.subTest(case=name):
                packet = self.make_packet(protocol, name, rssi, snr)
                message = formatter(packet)
                self.assertIsNotNone(message)
                payload = json.loads(message.payload)
                self.assertEqual(payload["payload"]["text"], "signal regression")
                self.assertEqual(
                    {key: payload[key] for key in ("rssi", "snr") if key in payload},
                    expected,
                )

    def test_meshtastic_json_omits_only_missing_metrics(self):
        formatter = MeshtasticMqttFormatter("msh", "US", "!12345678")
        self.assert_json_metrics(formatter.format_json, Protocol.MESHTASTIC)

    def test_meshcore_json_omits_only_missing_metrics(self):
        formatter = MeshCoreMqttFormatter("msh", "US", "!12345678")
        self.assert_json_metrics(formatter.format, Protocol.MESHCORE)


if __name__ == "__main__":
    unittest.main()
