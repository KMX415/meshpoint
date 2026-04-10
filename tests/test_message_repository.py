"""Tests for MessageRepository: save, dedup, and conversation queries."""

from __future__ import annotations

import asyncio
import unittest

from src.storage.database import DatabaseManager
from src.storage.message_repository import (
    BROADCAST_NODE_MC,
    BROADCAST_NODE_MT,
    Message,
    MessageRepository,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class TestMessageRepository(unittest.TestCase):
    """Integration tests using an in-memory SQLite database."""

    def setUp(self):
        self.db = DatabaseManager(":memory:")
        _run(self.db.connect())
        self.repo = MessageRepository(self.db)

    def tearDown(self):
        _run(self.db.disconnect())

    def test_save_sent(self):
        row_id = _run(self.repo.save_sent(
            text="hello",
            node_id="abc123",
            node_name="TestNode",
            protocol="meshtastic",
        ))
        self.assertGreater(row_id, 0)

    def test_save_received(self):
        row_id, is_dup = _run(self.repo.save_received(
            text="incoming",
            node_id="xyz789",
            node_name="Sender",
            protocol="meshcore",
            rssi=-75.0,
            snr=8.5,
        ))
        self.assertGreater(row_id, 0)
        self.assertFalse(is_dup)

    def test_dedup_increments_rx_count(self):
        _run(self.repo.save_received(
            text="first", node_id="n1", node_name="N",
            protocol="meshtastic", packet_id="PKT001",
            rssi=-90.0, snr=5.0,
        ))
        row_id, is_dup = _run(self.repo.save_received(
            text="first", node_id="n1", node_name="N",
            protocol="meshtastic", packet_id="PKT001",
            rssi=-85.0, snr=6.0,
        ))
        self.assertTrue(is_dup)

        msgs = _run(self.repo.get_conversation("n1"))
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].rx_count, 2)

    def test_dedup_keeps_stronger_signal(self):
        _run(self.repo.save_received(
            text="msg", node_id="n1", node_name="N",
            protocol="meshtastic", packet_id="PKT002",
            rssi=-80.0, snr=7.0,
        ))
        _run(self.repo.save_received(
            text="msg", node_id="n1", node_name="N",
            protocol="meshtastic", packet_id="PKT002",
            rssi=-95.0, snr=3.0,
        ))
        msgs = _run(self.repo.get_conversation("n1"))
        self.assertEqual(msgs[0].rssi, -80.0)

    def test_dedup_upgrades_to_stronger_signal(self):
        _run(self.repo.save_received(
            text="msg", node_id="n1", node_name="N",
            protocol="meshtastic", packet_id="PKT003",
            rssi=-95.0, snr=3.0,
        ))
        _run(self.repo.save_received(
            text="msg", node_id="n1", node_name="N",
            protocol="meshtastic", packet_id="PKT003",
            rssi=-70.0, snr=9.0,
        ))
        msgs = _run(self.repo.get_conversation("n1"))
        self.assertEqual(msgs[0].rssi, -70.0)
        self.assertEqual(msgs[0].snr, 9.0)
        self.assertEqual(msgs[0].rx_count, 2)

    def test_conversations_list(self):
        _run(self.repo.save_sent(
            text="hey", node_id="n1", node_name="Node1",
            protocol="meshtastic",
        ))
        _run(self.repo.save_received(
            text="hi", node_id="n2", node_name="Node2",
            protocol="meshcore",
        ))
        convos = _run(self.repo.get_conversations())
        self.assertEqual(len(convos), 2)
        node_ids = {c.node_id for c in convos}
        self.assertIn("n1", node_ids)
        self.assertIn("n2", node_ids)

    def test_message_to_dict_includes_signal(self):
        msg = Message(
            id=1, direction="received", text="test",
            node_id="n1", node_name="N", protocol="meshtastic",
            channel=0, timestamp="2026-01-01T00:00:00",
            status="delivered", packet_id="P1",
            rssi=-82.3, snr=7.1, rx_count=3,
        )
        d = msg.to_dict()
        self.assertEqual(d["rssi"], -82.3)
        self.assertEqual(d["snr"], 7.1)
        self.assertEqual(d["rx_count"], 3)

    def test_message_to_dict_omits_null_signal(self):
        msg = Message(
            id=1, direction="sent", text="test",
            node_id="n1", node_name="N", protocol="meshtastic",
            channel=0, timestamp="2026-01-01T00:00:00",
            status="sent", packet_id="P2",
        )
        d = msg.to_dict()
        self.assertNotIn("rssi", d)
        self.assertNotIn("snr", d)

    def test_broadcast_node_constants(self):
        self.assertEqual(BROADCAST_NODE_MT, "broadcast:meshtastic")
        self.assertEqual(BROADCAST_NODE_MC, "broadcast:meshcore")


if __name__ == "__main__":
    unittest.main()
