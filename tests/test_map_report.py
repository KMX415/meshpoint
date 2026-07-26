"""Tests for native, MQTT-only Meshtastic MapReport publishing."""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock

from meshtastic.protobuf import mqtt_pb2

from src.config import AppConfig, MqttConfig
from src.coordinator import PipelineCoordinator
from src.relay.map_report import (
    MAP_REPORT_PORTNUM,
    MapReportData,
    _round_coordinate,
    build_map_report_message,
)
from src.relay.mqtt_publisher import MqttPublisher


def _report(**overrides) -> MapReportData:
    values = {
        "node_id": 0x5F8FF3B0,
        "long_name": "Meshpoint2_SCM_KA",
        "short_name": "SCMK",
        "latitude": 48.933946,
        "longitude": 8.570711,
        "altitude": 180,
        "firmware_version": "0.7.7",
        "region": "EU_868",
        "modem_preset": "LONG_FAST",
        "primary_channel_name": "LongFast",
        "has_default_channel": True,
        "num_online_local_nodes": 3,
        "position_precision": 14,
    }
    values.update(overrides)
    return MapReportData(**values)


class TestMapReportFormat(unittest.TestCase):
    def test_builds_official_map_topic_and_service_envelope(self) -> None:
        message = build_map_report_message(
            _report(), topic_root="msh", mqtt_region="EU"
        )
        self.assertEqual(message.topic, "msh/EU/2/map/")

        envelope = mqtt_pb2.ServiceEnvelope()
        envelope.ParseFromString(message.payload)
        self.assertEqual(envelope.gateway_id, "!5f8ff3b0")
        self.assertEqual(envelope.channel_id, "LongFast")
        self.assertEqual(getattr(envelope.packet, "from"), 0x5F8FF3B0)
        self.assertEqual(envelope.packet.to, 0xFFFFFFFF)
        self.assertEqual(envelope.packet.decoded.portnum, MAP_REPORT_PORTNUM)

        report = mqtt_pb2.MapReport()
        report.ParseFromString(envelope.packet.decoded.payload)
        self.assertEqual(report.long_name, "Meshpoint2_SCM_KA")
        self.assertEqual(report.short_name, "SCMK")
        self.assertEqual(report.hw_model, 37)
        self.assertEqual(report.firmware_version, "0.7.7")
        self.assertEqual(report.position_precision, 14)
        self.assertEqual(report.num_online_local_nodes, 3)
        self.assertTrue(report.has_default_channel)
        self.assertTrue(report.has_opted_report_location)
        self.assertEqual(report.latitude_i, _round_coordinate(48.933946, 14))
        self.assertEqual(report.longitude_i, _round_coordinate(8.570711, 14))

    def test_bounds_strings_and_position_precision(self) -> None:
        message = build_map_report_message(
            _report(
                long_name="x" * 40,
                short_name="abcdef",
                firmware_version="v" * 30,
                position_precision=99,
            ),
            topic_root="msh",
            mqtt_region="US",
        )
        envelope = mqtt_pb2.ServiceEnvelope()
        envelope.ParseFromString(message.payload)
        report = mqtt_pb2.MapReport()
        report.ParseFromString(envelope.packet.decoded.payload)
        self.assertEqual(len(report.long_name), 24)
        self.assertEqual(len(report.short_name), 4)
        self.assertEqual(len(report.firmware_version), 17)
        self.assertEqual(report.position_precision, 15)

    def test_negative_coordinate_rounding_stays_signed(self) -> None:
        rounded = _round_coordinate(-74.0060, 14)
        self.assertLess(rounded, 0)
        self.assertGreaterEqual(rounded, -(2**31))


class TestMapReportPublisher(unittest.TestCase):
    def test_publish_uses_qos_one_and_tracks_runtime(self) -> None:
        publisher = MqttPublisher(
            MqttConfig(enabled=True), device_name="gateway"
        )
        client = MagicMock()
        client.publish.return_value.rc = 0
        publisher._client = client
        publisher._connected = True

        self.assertTrue(publisher.publish_map_report(_report()))
        _, kwargs = client.publish.call_args
        self.assertEqual(kwargs["qos"], 1)
        self.assertEqual(publisher.publish_count, 1)
        self.assertIsNotNone(
            publisher.get_runtime_status()["last_map_report_at"]
        )


class TestCoordinatorMapReport(unittest.IsolatedAsyncioTestCase):
    async def test_builds_report_from_meshpoint_config(self) -> None:
        config = AppConfig()
        config.device.latitude = 48.933946
        config.device.longitude = 8.570711
        config.device.altitude = 180
        config.radio.region = "EU_868"
        config.radio.frequency_mhz = 869.525
        config.transmit.node_id = 0x5F8FF3B0
        config.transmit.long_name = "Meshpoint2_SCM_KA"
        config.transmit.short_name = "SCMK"
        config.mqtt.map_reporting_enabled = True

        coordinator = PipelineCoordinator(config)
        coordinator._node_repo = MagicMock()
        coordinator._node_repo.get_active_count = AsyncMock(return_value=4)
        coordinator._mqtt = MagicMock()
        coordinator._mqtt.publish_map_report.return_value = True

        self.assertTrue(await coordinator._publish_map_report())
        report = coordinator._mqtt.publish_map_report.call_args.args[0]
        self.assertEqual(report.node_id, 0x5F8FF3B0)
        self.assertEqual(report.region, "EU_868")
        self.assertEqual(report.modem_preset, "LONG_FAST")
        self.assertTrue(report.has_default_channel)
        self.assertEqual(report.num_online_local_nodes, 4)
        coordinator._node_repo.get_active_count.assert_awaited_once_with(
            hours=2, protocol="meshtastic"
        )

    async def test_skips_report_without_location(self) -> None:
        config = AppConfig()
        config.transmit.node_id = 0x5F8FF3B0
        coordinator = PipelineCoordinator(config)
        coordinator._mqtt = MagicMock()

        self.assertFalse(await coordinator._publish_map_report())
        coordinator._mqtt.publish_map_report.assert_not_called()


if __name__ == "__main__":
    unittest.main()
