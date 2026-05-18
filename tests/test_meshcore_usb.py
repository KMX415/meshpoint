"""Tests for MeshCore USB capture: event adapter, config, and detection."""

from __future__ import annotations

import asyncio
import json
import unittest
from datetime import datetime, timezone

from src.config import (
    AppConfig,
    CaptureConfig,
    MeshcoreUsbConfig,
    _merge_dataclass,
)
from src.decode.crypto_service import CryptoService
from src.decode.meshcore_decoder import MeshcoreDecoder
from src.decode.meshcore_event_adapter import adapt_event
from src.models.packet import Packet, PacketType, Protocol
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
            "SNR": 11.25,
            "timestamp": 1700000000,
        })
        pkt = adapt_event(raw)
        self.assertIsNotNone(pkt)
        self.assertEqual(pkt.packet_type, PacketType.TEXT)
        self.assertEqual(pkt.destination_id, "broadcast")
        self.assertEqual(pkt.channel_hash, 2)
        self.assertEqual(pkt.decoded_payload["channel"], 2)
        self.assertEqual(pkt.signal.snr, 11.25)

    def test_channel_message_parses_sender_from_text(self):
        raw = self._make_envelope("channel_message", {
            "text": "Alice: Hello everyone",
            "channel_idx": 0,
            "timestamp": 1700000000,
        })
        pkt = adapt_event(raw)
        self.assertIsNotNone(pkt)
        self.assertEqual(pkt.decoded_payload["text"], "Hello everyone")
        self.assertEqual(pkt.decoded_payload["long_name"], "Alice")
        self.assertEqual(pkt.source_id, "mc:Alice")
        self.assertEqual(pkt.destination_id, "broadcast")

    def test_channel_message_with_sender_name_field(self):
        raw = self._make_envelope("channel_message", {
            "sender_name": "Bob",
            "text": "Some message",
            "channel_idx": 1,
        })
        pkt = adapt_event(raw)
        self.assertIsNotNone(pkt)
        self.assertEqual(pkt.decoded_payload["long_name"], "Bob")
        self.assertEqual(pkt.source_id, "mc:Bob")

    def test_contact_message_has_long_name(self):
        raw = self._make_envelope("contact_message", {
            "pubkey_prefix": "aabb1122",
            "contact_name": "Charlie",
            "text": "DM text",
        })
        pkt = adapt_event(raw)
        self.assertIsNotNone(pkt)
        self.assertEqual(pkt.decoded_payload["long_name"], "Charlie")

    def test_advertisement(self):
        raw = self._make_envelope("advertisement", {
            "public_key": "abcdef1234567890abcdef",
            "adv_name": "TestNode",
            "adv_lat": 43.9091,
            "adv_lon": -72.2207,
        })
        pkt = adapt_event(raw)
        self.assertIsNotNone(pkt)
        self.assertEqual(pkt.packet_type, PacketType.NODEINFO)
        self.assertEqual(pkt.source_id, "abcdef123456")
        self.assertEqual(pkt.destination_id, "broadcast")
        self.assertEqual(pkt.decoded_payload["long_name"], "TestNode")
        self.assertEqual(pkt.decoded_payload["short_name"], "Test")
        self.assertAlmostEqual(pkt.decoded_payload["latitude"], 43.9091)
        self.assertAlmostEqual(pkt.decoded_payload["longitude"], -72.2207)

    def test_advertisement_accepts_name_alias(self):
        raw = self._make_envelope("advertisement", {
            "public_key": "abcdef1234567890abcdef",
            "name": "AliasNode",
        })
        pkt = adapt_event(raw)
        self.assertIsNotNone(pkt)
        self.assertEqual(pkt.packet_type, PacketType.NODEINFO)
        self.assertEqual(pkt.source_id, "abcdef123456")
        self.assertEqual(pkt.decoded_payload["long_name"], "AliasNode")
        self.assertEqual(pkt.decoded_payload["short_name"], "Alia")

    def test_advertisement_accepts_nested_name_alias(self):
        raw = self._make_envelope("advertisement", {
            "public_key": "abcdef1234567890abcdef",
            "advert": {"longName": "NestedRepeater"},
        })
        pkt = adapt_event(raw)
        self.assertIsNotNone(pkt)
        self.assertEqual(pkt.packet_type, PacketType.NODEINFO)
        self.assertEqual(pkt.source_id, "abcdef123456")
        self.assertEqual(pkt.decoded_payload["long_name"], "NestedRepeater")
        self.assertEqual(pkt.decoded_payload["short_name"], "Nest")

    def test_advertisement_without_real_name_does_not_store_id_as_name(self):
        raw = self._make_envelope("advertisement", {
            "public_key": "abcdef1234567890abcdef",
        })
        pkt = adapt_event(raw)
        self.assertIsNotNone(pkt)
        self.assertEqual(pkt.packet_type, PacketType.NODEINFO)
        self.assertEqual(pkt.source_id, "abcdef123456")
        self.assertNotIn("long_name", pkt.decoded_payload)
        self.assertNotIn("short_name", pkt.decoded_payload)

    def test_advertisement_no_coords(self):
        raw = self._make_envelope("advertisement", {
            "public_key": "abcdef1234567890abcdef",
            "adv_lat": 0.0,
            "adv_lon": 0.0,
        })
        pkt = adapt_event(raw)
        self.assertIsNotNone(pkt)
        self.assertNotIn("latitude", pkt.decoded_payload)
        self.assertNotIn("longitude", pkt.decoded_payload)

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

    def test_rx_log_data(self):
        raw = self._make_envelope("rx_log_data", {
            "snr": 9.5,
            "rssi": -72.0,
            "payload": "f593010380abcdef",
            "payload_length": 32,
        })
        pkt = adapt_event(raw)
        self.assertIsNotNone(pkt)
        self.assertEqual(pkt.protocol, Protocol.MESHCORE)
        self.assertEqual(pkt.packet_type, PacketType.UNKNOWN)
        self.assertEqual(pkt.decoded_payload["raw_hex"], "f593010380abcdef")
        self.assertEqual(pkt.decoded_payload["payload_length"], 32)
        self.assertEqual(pkt.signal.rssi, -72.0)
        self.assertEqual(pkt.signal.snr, 9.5)
        self.assertEqual(pkt.source_id, "rf_log")

    def test_rx_log_data_raw_hex_fallback(self):
        raw = self._make_envelope("rx_log_data", {
            "snr": 5.0,
            "rssi": -90.0,
            "raw_hex": "aabb001122",
        })
        pkt = adapt_event(raw)
        self.assertIsNotNone(pkt)
        self.assertEqual(pkt.decoded_payload["raw_hex"], "aabb001122")

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


class TestMeshcoreDecoderNodeExtraction(unittest.TestCase):
    """Verify ``extract_node_update`` lifts MeshCore advert position onto Node.

    Regression coverage for the bug where MeshCore nodes never appeared on
    the dashboard map: their lat/lon rides on the advertisement (classified
    by the event adapter as ``PacketType.NODEINFO``), but the extractor only
    consumed positions from ``PacketType.POSITION`` packets, so the lat/lon
    silently dropped on the floor before the node repository write.
    """

    def setUp(self) -> None:
        self._decoder = MeshcoreDecoder(CryptoService())

    @staticmethod
    def _make_envelope(event_type: str, payload: dict) -> bytes:
        return json.dumps({
            "event_type": event_type,
            "payload": payload,
        }).encode("utf-8")

    def _adapt_advertisement(self, payload: dict) -> Packet:
        pkt = adapt_event(self._make_envelope("advertisement", payload))
        assert pkt is not None, "advertisement should adapt to a Packet"
        return pkt

    def test_advertisement_with_position_yields_positioned_node(self):
        pkt = self._adapt_advertisement({
            "public_key": "abcdef1234567890abcdef",
            "adv_name": "TestNode",
            "adv_lat": 43.9091,
            "adv_lon": -72.2207,
        })

        node = self._decoder.extract_node_update(pkt)

        self.assertIsNotNone(node)
        self.assertTrue(node.has_position)
        self.assertAlmostEqual(node.latitude, 43.9091)
        self.assertAlmostEqual(node.longitude, -72.2207)
        self.assertEqual(node.long_name, "TestNode")
        self.assertEqual(node.protocol, Protocol.MESHCORE.value)

    def test_advertisement_without_position_yields_node_without_position(self):
        pkt = self._adapt_advertisement({
            "public_key": "abcdef1234567890abcdef",
            "adv_name": "TestNode",
            "adv_lat": 0.0,
            "adv_lon": 0.0,
        })

        node = self._decoder.extract_node_update(pkt)

        self.assertIsNotNone(node)
        self.assertFalse(node.has_position)
        self.assertIsNone(node.latitude)
        self.assertIsNone(node.longitude)
        self.assertEqual(node.long_name, "TestNode")

    def test_position_packet_still_extracts_lat_lon(self):
        """Regression guard for the original ``PacketType.POSITION`` path."""
        from datetime import datetime, timezone

        pkt = Packet(
            packet_id="0001",
            source_id="abcd",
            destination_id="broadcast",
            protocol=Protocol.MESHCORE,
            packet_type=PacketType.POSITION,
            decoded_payload={"latitude": 12.34, "longitude": -56.78},
            timestamp=datetime.now(timezone.utc),
            decrypted=True,
        )

        node = self._decoder.extract_node_update(pkt)

        self.assertIsNotNone(node)
        self.assertTrue(node.has_position)
        self.assertAlmostEqual(node.latitude, 12.34)
        self.assertAlmostEqual(node.longitude, -56.78)


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


class TestMeshcoreUsbStartupRetry(unittest.IsolatedAsyncioTestCase):
    """Verify the source schedules a background reconnect on initial fail."""

    async def test_failed_initial_connect_schedules_reconnect_task(self):
        """If _connect() leaves _connected False, a reconnect task spawns."""
        from src.capture.meshcore_usb_source import MeshcoreUsbCaptureSource

        source = MeshcoreUsbCaptureSource(
            serial_port="/dev/ttyFAKE", auto_detect=False
        )

        async def fake_resolve_port():
            return "/dev/ttyFAKE"

        async def fake_connect(port):
            source._connected = False

        # Replace _reconnect with a no-op that yields once so the task
        # exists long enough to be observed, then exits cleanly.
        async def fake_reconnect():
            await asyncio.sleep(0)

        source._resolve_port = fake_resolve_port  # type: ignore[assignment]
        source._connect = fake_connect  # type: ignore[assignment]
        source._reconnect = fake_reconnect  # type: ignore[assignment]

        await source.start()
        try:
            self.assertIsNotNone(source._reconnect_task)
            self.assertFalse(source._connected)
            self.assertIsNone(source._health_task)
        finally:
            await source.stop()

    async def test_successful_initial_connect_skips_reconnect_task(self):
        """If _connect() succeeds, no reconnect task is scheduled."""
        from src.capture.meshcore_usb_source import MeshcoreUsbCaptureSource

        source = MeshcoreUsbCaptureSource(
            serial_port="/dev/ttyFAKE", auto_detect=False
        )

        async def fake_resolve_port():
            return "/dev/ttyFAKE"

        async def fake_connect(port):
            source._connected = True

        async def fake_health_loop():
            await asyncio.sleep(60)

        source._resolve_port = fake_resolve_port  # type: ignore[assignment]
        source._connect = fake_connect  # type: ignore[assignment]
        source._health_check_loop = fake_health_loop  # type: ignore[assignment]

        await source.start()
        try:
            self.assertIsNone(source._reconnect_task)
            self.assertTrue(source._connected)
            self.assertIsNotNone(source._health_task)
        finally:
            await source.stop()

    async def test_recent_event_skips_health_probe(self):
        """If an event arrived recently, _has_recent_event_activity returns True."""
        from src.capture.meshcore_usb_source import MeshcoreUsbCaptureSource

        source = MeshcoreUsbCaptureSource(
            serial_port="/dev/ttyFAKE", auto_detect=False
        )

        # No events ever -> not recent
        self.assertFalse(source._has_recent_event_activity())

        # Mark as just-now
        source._last_event_at = asyncio.get_event_loop().time()
        self.assertTrue(source._has_recent_event_activity())

        # Mark as ancient (10 minutes ago)
        source._last_event_at = (
            asyncio.get_event_loop().time() - 600.0
        )
        self.assertFalse(source._has_recent_event_activity())

    async def test_on_event_records_timestamp(self):
        """_on_event must update _last_event_at as proof of life."""
        from src.capture.meshcore_usb_source import MeshcoreUsbCaptureSource

        source = MeshcoreUsbCaptureSource(
            serial_port="/dev/ttyFAKE", auto_detect=False
        )
        source._running = True
        self.assertEqual(source._last_event_at, 0.0)

        class _FakeEvent:
            pass

        await source._on_event(_FakeEvent())
        self.assertGreater(source._last_event_at, 0.0)

    async def test_stop_cancels_pending_reconnect_task(self):
        """stop() must cancel a still-running reconnect task without hanging."""
        from src.capture.meshcore_usb_source import MeshcoreUsbCaptureSource

        source = MeshcoreUsbCaptureSource(
            serial_port="/dev/ttyFAKE", auto_detect=False
        )

        async def fake_resolve_port():
            return "/dev/ttyFAKE"

        async def fake_connect(port):
            source._connected = False

        reconnect_started = asyncio.Event()

        async def slow_reconnect():
            reconnect_started.set()
            await asyncio.sleep(60)

        source._resolve_port = fake_resolve_port  # type: ignore[assignment]
        source._connect = fake_connect  # type: ignore[assignment]
        source._reconnect = slow_reconnect  # type: ignore[assignment]

        await source.start()
        await reconnect_started.wait()
        await asyncio.wait_for(source.stop(), timeout=2.0)
        self.assertIsNone(source._reconnect_task)


if __name__ == "__main__":
    unittest.main()
