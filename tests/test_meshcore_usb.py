"""Tests for MeshCore USB capture: event adapter, config, and detection."""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone

from src.config import (
    AppConfig,
    CaptureConfig,
    MeshcoreUsbConfig,
    _merge_dataclass,
)
from src.decode.meshcore_event_adapter import adapt_event
from src.models.packet import PacketType, Protocol
from src.models.signal import SignalMetrics


class TestMeshcoreEventAdapter(unittest.TestCase):
    """Verify JSON-encoded meshcore events convert to Packet objects."""

    def _make_envelope(self, event_type: str, payload: dict) -> bytes:
        return json.dumps({
            "event_type": event_type,
            "payload": payload,
        }).encode("utf-8")

    def test_contact_message(self):
        raw = self._make_envelope("contact_message", {
            "pubkey_prefix": "a1b2c3d4e5f6",
            "text": "Hello from MeshCore",
            "timestamp": 1700000000,
        })
        pkt = adapt_event(raw)
        self.assertIsNotNone(pkt)
        self.assertEqual(pkt.protocol, Protocol.MESHCORE)
        self.assertEqual(pkt.packet_type, PacketType.TEXT)
        self.assertEqual(pkt.source_id, "a1b2c3d4e5f6")
        self.assertEqual(pkt.decoded_payload["text"], "Hello from MeshCore")
        self.assertTrue(pkt.decrypted)

    def test_channel_message(self):
        raw = self._make_envelope("channel_message", {
            "text": "Channel broadcast",
            "channel_idx": 2,
            "timestamp": 1700000000,
        })
        pkt = adapt_event(raw)
        self.assertIsNotNone(pkt)
        self.assertEqual(pkt.packet_type, PacketType.TEXT)
        self.assertEqual(pkt.destination_id, "channel:2")
        self.assertEqual(pkt.channel_hash, 2)
        self.assertEqual(pkt.decoded_payload["channel"], 2)

    def test_advertisement(self):
        raw = self._make_envelope("advertisement", {
            "public_key": "abcdef1234567890abcdef",
        })
        pkt = adapt_event(raw)
        self.assertIsNotNone(pkt)
        self.assertEqual(pkt.packet_type, PacketType.NODEINFO)
        self.assertEqual(pkt.source_id, "abcdef123456")
        self.assertEqual(pkt.destination_id, "broadcast")

    def test_raw_data(self):
        raw = self._make_envelope("raw_data", {
            "rssi": -85.0,
            "snr": 7.5,
            "payload": "deadbeef",
        })
        pkt = adapt_event(raw)
        self.assertIsNotNone(pkt)
        self.assertEqual(pkt.packet_type, PacketType.UNKNOWN)
        self.assertEqual(pkt.decoded_payload["raw_hex"], "deadbeef")

    def test_unknown_event_returns_none(self):
        raw = self._make_envelope("battery_info", {"level": 85})
        pkt = adapt_event(raw)
        self.assertIsNone(pkt)

    def test_invalid_json_returns_none(self):
        pkt = adapt_event(b"not json at all")
        self.assertIsNone(pkt)

    def test_signal_passthrough(self):
        raw = self._make_envelope("contact_message", {
            "pubkey_prefix": "aabbccdd",
            "text": "hi",
        })
        signal = SignalMetrics(
            rssi=-75.0, snr=10.0, frequency_mhz=906.875,
            spreading_factor=11, bandwidth_khz=62.5,
        )
        pkt = adapt_event(raw, signal=signal)
        self.assertIsNotNone(pkt)
        self.assertEqual(pkt.signal.rssi, -75.0)

    def test_timestamp_parsing(self):
        ts = 1700000000
        raw = self._make_envelope("contact_message", {
            "pubkey_prefix": "aabb",
            "text": "t",
            "timestamp": ts,
        })
        pkt = adapt_event(raw)
        expected = datetime.fromtimestamp(ts, tz=timezone.utc)
        self.assertEqual(pkt.timestamp, expected)

    def test_missing_timestamp_uses_utc_now(self):
        raw = self._make_envelope("contact_message", {
            "pubkey_prefix": "aabb",
            "text": "t",
        })
        pkt = adapt_event(raw)
        self.assertIsNotNone(pkt.timestamp)
        self.assertEqual(pkt.timestamp.tzinfo, timezone.utc)


class TestMeshcoreUsbConfig(unittest.TestCase):
    """Verify MeshcoreUsbConfig defaults and YAML merging."""

    def test_default_values(self):
        cfg = MeshcoreUsbConfig()
        self.assertIsNone(cfg.serial_port)
        self.assertEqual(cfg.baud_rate, 115200)
        self.assertTrue(cfg.auto_detect)

    def test_capture_config_has_meshcore_usb(self):
        cap = CaptureConfig()
        self.assertIsInstance(cap.meshcore_usb, MeshcoreUsbConfig)

    def test_nested_dataclass_merge(self):
        cfg = AppConfig()
        overrides = {
            "meshcore_usb": {
                "serial_port": "/dev/ttyUSB1",
                "auto_detect": False,
            }
        }
        _merge_dataclass(cfg.capture, overrides)
        self.assertEqual(cfg.capture.meshcore_usb.serial_port, "/dev/ttyUSB1")
        self.assertFalse(cfg.capture.meshcore_usb.auto_detect)
        self.assertEqual(cfg.capture.meshcore_usb.baud_rate, 115200)

    def test_nested_merge_preserves_other_fields(self):
        cfg = AppConfig()
        overrides = {"meshcore_usb": {"baud_rate": 9600}}
        _merge_dataclass(cfg.capture, overrides)
        self.assertEqual(cfg.capture.meshcore_usb.baud_rate, 9600)
        self.assertTrue(cfg.capture.meshcore_usb.auto_detect)


class TestFindSerialCandidates(unittest.TestCase):
    """Verify port filtering in meshcore_usb_detect."""

    def test_exclude_ports(self):
        from src.capture.meshcore_usb_detect import find_serial_candidates
        result = find_serial_candidates(
            exclude_ports=frozenset(["/dev/ttyUSB0"])
        )
        for port in result:
            self.assertNotEqual(port, "/dev/ttyUSB0")


if __name__ == "__main__":
    unittest.main()
