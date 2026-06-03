"""Tests for live message display name resolution."""

from __future__ import annotations

import asyncio
import unittest

from src.api.message_name_resolver import MessageNameResolver
from src.models.node import Node
from src.models.packet import Packet, PacketType, Protocol, SignalMetrics
from src.storage.database import DatabaseManager
from src.storage.message_repository import MessageRepository
from src.storage.node_repository import NodeRepository
from src.storage.packet_repository import PacketRepository


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestMessageNameResolver(unittest.TestCase):
    def setUp(self) -> None:
        self.db = DatabaseManager(":memory:")
        _run(self.db.connect())
        self.node_repo = NodeRepository(self.db)
        self.message_repo = MessageRepository(self.db)
        self.packet_repo = PacketRepository(self.db)
        self.resolver = MessageNameResolver(
            self.node_repo, packet_repo=self.packet_repo
        )

    def tearDown(self) -> None:
        _run(self.db.disconnect())

    def test_conversation_uses_current_node_name_not_stored_message_name(self):
        _run(self.node_repo.upsert(
            Node(
                node_id="7d8b98a9",
                long_name="Guziii",
                protocol="meshtastic",
            )
        ))
        _run(self.message_repo.save_received(
            text="Hello",
            node_id="7d8b98a9",
            node_name="Guzii",
            protocol="meshtastic",
        ))

        convos = _run(self.message_repo.get_conversations())
        self.assertEqual(len(convos), 1)
        raw = convos[0].to_dict()
        enriched = _run(self.resolver.apply_to_conversation_dict(raw))
        self.assertEqual(enriched["node_name"], "Guziii")

    def test_message_history_uses_current_node_name(self):
        _run(self.node_repo.upsert(
            Node(
                node_id="7d8b98a9",
                long_name="Guziii",
                protocol="meshtastic",
            )
        ))
        _run(self.message_repo.save_received(
            text="Hello",
            node_id="7d8b98a9",
            node_name="Guzii",
            protocol="meshtastic",
        ))

        messages = _run(self.message_repo.get_conversation("7d8b98a9"))
        raw = messages[0].to_dict()
        enriched = _run(self.resolver.apply_to_message_dict(raw))
        self.assertEqual(enriched["node_name"], "Guziii")

    def test_broadcast_channel_does_not_force_sender_label_broadcast(self):
        _run(self.node_repo.upsert(
            Node(
                node_id="a1b2c3d4",
                long_name="TestNode",
                protocol="meshtastic",
            )
        ))
        async def _seed_packet() -> None:
            await self.packet_repo.insert(Packet(
                packet_id="pkt-bcast-1",
                source_id="a1b2c3d4",
                destination_id="ffffffff",
                protocol=Protocol.MESHTASTIC,
                packet_type=PacketType.TEXT,
                signal=SignalMetrics(
                    rssi=-50.0,
                    snr=8.0,
                    frequency_mhz=906.875,
                    spreading_factor=11,
                    bandwidth_khz=250,
                ),
            ))
            await self.db.commit()

        _run(_seed_packet())
        _run(self.message_repo.save_received(
            text="Hey",
            node_id="broadcast:meshtastic:0",
            node_name="Broadcast",
            protocol="meshtastic",
            packet_id="pkt-bcast-1",
        ))

        messages = _run(self.message_repo.get_conversation("broadcast:meshtastic:0"))
        raw = messages[0].to_dict()
        enriched = _run(self.resolver.apply_to_message_dict(raw))
        self.assertEqual(enriched["node_name"], "TestNode")

    def test_resolve_sender_by_source_id_for_broadcast_lookup(self):
        _run(self.node_repo.upsert(
            Node(
                node_id="a1b2c3d4",
                long_name="TestNode",
                protocol="meshtastic",
            )
        ))
        name = _run(self.resolver.resolve("a1b2c3d4", "meshtastic", ""))
        self.assertEqual(name, "TestNode")


if __name__ == "__main__":
    unittest.main()
