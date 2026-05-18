"""Tests for MQTT publisher logging and gateway ID behavior."""

from __future__ import annotations

import unittest

from src.config import MqttConfig
from src.relay.mqtt_publisher import MqttPublisher, _generate_gateway_id


class TestGatewayId(unittest.TestCase):
    def test_gateway_id_is_deterministic_and_case_insensitive(self):
        lower = _generate_gateway_id("meshpoint-alpha")
        upper = _generate_gateway_id("MESHPOINT-ALPHA")
        self.assertEqual(lower, upper)
        self.assertTrue(lower.startswith("!"))
        self.assertEqual(len(lower), 9)


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


if __name__ == "__main__":
    unittest.main()
