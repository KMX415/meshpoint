from __future__ import annotations

import asyncio
import unittest

from src.models.node import Node
from src.storage.database import DatabaseManager
from src.storage.node_repository import NodeRepository


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestNodeRepository(unittest.TestCase):
    def setUp(self) -> None:
        self.db = DatabaseManager(":memory:")
        _run(self.db.connect())
        self.repo = NodeRepository(self.db)

    def tearDown(self) -> None:
        _run(self.db.disconnect())

    def test_meshcore_pubkey_placeholder_name_is_replaced(self):
        node_id = "abcdef123456"
        _run(self.repo.upsert(
            Node(
                node_id=node_id,
                long_name=node_id,
                short_name=node_id[:4],
                protocol="meshcore",
            )
        ))

        _run(self.repo.upsert(
            Node(
                node_id=node_id,
                long_name="Trail Relay",
                short_name="Trai",
                protocol="meshcore",
            )
        ))

        node = _run(self.repo.get_by_id(node_id))
        self.assertIsNotNone(node)
        self.assertEqual(node.long_name, "Trail Relay")

    def test_existing_real_name_is_kept(self):
        node_id = "abcdef123456"
        _run(self.repo.upsert(
            Node(
                node_id=node_id,
                long_name="Trail Relay",
                protocol="meshcore",
            )
        ))

        _run(self.repo.upsert(
            Node(
                node_id=node_id,
                long_name="Other Name",
                protocol="meshcore",
            )
        ))

        node = _run(self.repo.get_by_id(node_id))
        self.assertIsNotNone(node)
        self.assertEqual(node.long_name, "Trail Relay")

    def test_delete_phantom_rows_removes_unidentified_zero_packet_nodes(self) -> None:
        now = "2026-05-19T12:00:00+00:00"
        _run(
            self.db.execute(
                """
                INSERT INTO nodes (
                    node_id, long_name, short_name, protocol,
                    last_heard, first_seen, packet_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("phantom1", None, None, "meshtastic", now, now, 0),
            )
        )
        _run(
            self.db.execute(
                """
                INSERT INTO nodes (
                    node_id, long_name, short_name, protocol,
                    last_heard, first_seen, packet_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("real1", "Tower Relay", "Twr", "meshtastic", now, now, 0),
            )
        )
        _run(
            self.db.execute(
                """
                INSERT INTO nodes (
                    node_id, long_name, short_name, protocol,
                    last_heard, first_seen, packet_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("heard1", None, None, "meshtastic", now, now, 3),
            )
        )
        _run(self.db.commit())

        removed = _run(self.repo.delete_phantom_rows())
        self.assertEqual(removed, 1)
        self.assertIsNone(_run(self.repo.get_by_id("phantom1")))
        self.assertIsNotNone(_run(self.repo.get_by_id("real1")))
        self.assertIsNotNone(_run(self.repo.get_by_id("heard1")))

    def test_count_phantom_rows_matches_delete_predicate(self) -> None:
        now = "2026-05-19T12:00:00+00:00"
        _run(
            self.db.execute(
                """
                INSERT INTO nodes (
                    node_id, long_name, short_name, protocol,
                    last_heard, first_seen, packet_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                ("p2", "   ", None, "meshtastic", now, now, 0),
            )
        )
        _run(self.db.commit())
        self.assertEqual(_run(self.repo.count_phantom_rows()), 1)

    def test_meshcore_display_name_ignores_id_placeholder(self):
        node = Node(
            node_id="abcdef123456",
            long_name="abcdef123456",
            short_name="abcd",
            protocol="meshcore",
        )

        self.assertEqual(node.display_name, "!abcdef123456")


if __name__ == "__main__":
    unittest.main()
