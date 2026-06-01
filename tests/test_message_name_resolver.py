"""Tests for live message display name resolution."""

from __future__ import annotations

import asyncio
import unittest

from src.api.message_name_resolver import MessageNameResolver
from src.models.node import Node
from src.storage.database import DatabaseManager
from src.storage.message_repository import MessageRepository
from src.storage.node_repository import NodeRepository


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
        self.resolver = MessageNameResolver(self.node_repo)

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


if __name__ == "__main__":
    unittest.main()
