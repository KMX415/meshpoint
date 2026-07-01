"""Tests for MQTT publisher logging and gateway ID behavior."""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock

from src.config import MqttConfig
from src.models.packet import PacketType
from src.relay.mqtt_publisher import HomeAssistantDiscovery, MqttPublisher, _generate_gateway_id


class TestGatewayId(unittest.TestCase):
    def test_gateway_id_is_deterministic_and_case_insensitive(self):
        lower = _generate_gateway_id("meshpoint-alpha")
        upper = _generate_gateway_id("MESHPOINT-ALPHA")
        self.assertEqual(lower, upper)
        self.assertTrue(lower.startswith("!"))
        self.assertEqual(len(lower), 9)

    def test_config_override_used_by_publisher(self) -> None:
        cfg = MqttConfig(enabled=True, gateway_id="aabbccdd")
        pub = MqttPublisher(cfg, device_name="ignored")
        self.assertEqual(pub.gateway_id, "!aabbccdd")


class TestHomeAssistantState(unittest.TestCase):
    def test_telemetry_publishes_retained_json_state(self):
        client = MagicMock()
        ha = HomeAssistantDiscovery(client, "!deadbeef")
        packet = MagicMock()
        packet.source_id = "abcd1234"
        packet.packet_type = PacketType.TELEMETRY
        packet.decoded_payload = {
            "battery_level": 85,
            "temperature": 22.5,
        }

        ha.publish_state(packet)

        client.publish.assert_called_once()
        topic, body = client.publish.call_args[0][:2]
        self.assertEqual(topic, "meshpoint/abcd1234/telemetry")
        self.assertEqual(json.loads(body)["battery_level"], 85)
        self.assertEqual(client.publish.call_args[1].get("retain"), True)

    def test_position_publishes_retained_json_state(self):
        client = MagicMock()
        ha = HomeAssistantDiscovery(client, "!deadbeef")
        packet = MagicMock()
        packet.source_id = "abcd1234"
        packet.packet_type = PacketType.POSITION
        packet.decoded_payload = {
            "latitude": 40.7,
            "longitude": -74.0,
            "altitude": 10,
        }

        ha.publish_state(packet)

        topic, body = client.publish.call_args[0][:2]
        self.assertEqual(topic, "meshpoint/abcd1234/position")
        parsed = json.loads(body)
        self.assertEqual(parsed["latitude"], 40.7)
        self.assertEqual(parsed["longitude"], -74.0)
        self.assertEqual(parsed["altitude"], 10)


class TestMqttPublisherLogging(unittest.TestCase):
    def test_on_connect_logs_start_message(self):
        pub = MqttPublisher(MqttConfig(enabled=True), device_name="meshpoint-alpha")
        with self.assertLogs("src.relay.mqtt_publisher", level="INFO") as logs:
            pub._on_connect(client=None, userdata=None, flags=None, rc=0)
        self.assertTrue(pub.connected)
        self.assertTrue(
            any("MQTT publisher started as !" in msg for msg in logs.output),
            logs.output,
        )

    def test_runtime_status_tracks_connect_and_disconnect(self) -> None:
        pub = MqttPublisher(MqttConfig(enabled=True), device_name="meshpoint-alpha")
        pub._on_connect(client=None, userdata=None, flags=None, rc=0)
        status = pub.get_runtime_status()
        self.assertTrue(status["connected"])
        self.assertIsNotNone(status["connected_since"])
        pub._on_disconnect(client=None, userdata=None, rc=7)
        status = pub.get_runtime_status()
        self.assertFalse(status["connected"])
        self.assertEqual(status["disconnect_count"], 1)
        self.assertEqual(status["last_disconnect_rc"], 7)


if __name__ == "__main__":
    unittest.main()
