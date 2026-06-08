"""Unit tests for src/api/alert_emitter.py."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.api.alert_emitter import (
    BATTERY_LOW_PERCENT,
    ONLINE_THRESHOLD,
    AlertEmitter,
    build_alert_payload,
    is_node_online,
)
from src.models.packet import Packet, PacketType, Protocol


class TestBuildAlertPayload(unittest.TestCase):

    def test_includes_event_type_alert(self) -> None:
        payload = build_alert_payload(
            "node_offline",
            node_id="abc123",
            title="Node offline",
            body="Node abc123 has not been heard for 2+ hours.",
        )
        self.assertEqual(payload["event_type"], "alert")
        self.assertEqual(payload["alert_kind"], "node_offline")
        self.assertEqual(payload["node_id"], "abc123")
        self.assertIn("timestamp", payload)


class TestIsNodeOnline(unittest.TestCase):

    def test_recent_heard_is_online(self) -> None:
        now = datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc)
        heard = (now - timedelta(hours=1)).isoformat()
        self.assertTrue(is_node_online(heard, now=now))

    def test_stale_heard_is_offline(self) -> None:
        now = datetime(2026, 6, 2, 12, 0, tzinfo=timezone.utc)
        heard = (now - ONLINE_THRESHOLD - timedelta(minutes=1)).isoformat()
        self.assertFalse(is_node_online(heard, now=now))

    def test_missing_heard_is_offline(self) -> None:
        self.assertFalse(is_node_online(None))


class TestAlertEmitterBattery(unittest.IsolatedAsyncioTestCase):

    async def test_emits_battery_low_for_telemetry(self) -> None:
        ws = MagicMock()
        ws.broadcast = AsyncMock()
        repo = MagicMock()
        emitter = AlertEmitter(repo, ws)

        packet = Packet(
            packet_id="p1",
            source_id="node1",
            destination_id="broadcast",
            protocol=Protocol.MESHTASTIC,
            packet_type=PacketType.TELEMETRY,
            decoded_payload={
                "battery_level": BATTERY_LOW_PERCENT,
                "long_name": "Test Node",
            },
        )
        await emitter._handle_packet(packet)

        ws.broadcast.assert_awaited_once()
        args = ws.broadcast.await_args.args
        self.assertEqual(args[0], "alert")
        self.assertEqual(args[1]["alert_kind"], "battery_low")
        self.assertEqual(args[1]["battery_level"], 20)

    async def test_battery_alert_respects_cooldown(self) -> None:
        ws = MagicMock()
        ws.broadcast = AsyncMock()
        repo = MagicMock()
        emitter = AlertEmitter(repo, ws)

        packet = Packet(
            packet_id="p1",
            source_id="node1",
            destination_id="broadcast",
            protocol=Protocol.MESHTASTIC,
            packet_type=PacketType.TELEMETRY,
            decoded_payload={"battery_level": 10},
        )
        await emitter._handle_packet(packet)
        await emitter._handle_packet(packet)
        self.assertEqual(ws.broadcast.await_count, 1)


class TestAlertEmitterOnlineTransition(unittest.IsolatedAsyncioTestCase):

    async def test_node_online_only_after_explicit_offline(self) -> None:
        ws = MagicMock()
        ws.broadcast = AsyncMock()
        repo = MagicMock()
        emitter = AlertEmitter(repo, ws)
        emitter._online_state["node1"] = False

        packet = Packet(
            packet_id="p1",
            source_id="node1",
            destination_id="broadcast",
            protocol=Protocol.MESHTASTIC,
            packet_type=PacketType.TEXT,
            decoded_payload={"long_name": "Alpha"},
        )
        await emitter._handle_packet(packet)

        ws.broadcast.assert_awaited_once()
        self.assertEqual(ws.broadcast.await_args.args[1]["alert_kind"], "node_online")

    async def test_new_node_does_not_emit_online_alert(self) -> None:
        ws = MagicMock()
        ws.broadcast = AsyncMock()
        repo = MagicMock()
        emitter = AlertEmitter(repo, ws)

        packet = Packet(
            packet_id="p1",
            source_id="newnode",
            destination_id="broadcast",
            protocol=Protocol.MESHTASTIC,
            packet_type=PacketType.TEXT,
        )
        await emitter._handle_packet(packet)
        ws.broadcast.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
