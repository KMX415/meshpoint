"""Coverage map aggregation for GET /api/nodes/coverage."""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta, timezone

from src.models.node import Node
from src.storage.database import DatabaseManager
from src.storage.node_repository import NodeRepository


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestNodeCoverage(unittest.TestCase):
    def setUp(self) -> None:
        self.db = DatabaseManager(":memory:")
        _run(self.db.connect())
        self.repo = NodeRepository(self.db)

    def tearDown(self) -> None:
        _run(self.db.disconnect())

    def _insert_packet(
        self,
        packet_id: str,
        source_id: str,
        rssi: float,
        *,
        hours_ago: float = 1,
    ) -> None:
        ts = (
            datetime.now(timezone.utc) - timedelta(hours=hours_ago)
        ).isoformat()
        _run(
            self.db.execute(
                """
                INSERT INTO packets (
                    packet_id, source_id, destination_id, protocol,
                    packet_type, hop_limit, hop_start, channel_hash,
                    want_ack, via_mqtt, relay_node, decrypted,
                    rssi, snr, capture_source, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    packet_id, source_id, "ffffffff", "meshtastic", "text",
                    3, 3, 8, 0, 0, 0, 1,
                    rssi, 5.0, "concentrator", ts,
                ),
            )
        )

    def test_plotted_nodes_include_rssi_aggregates(self) -> None:
        _run(self.repo.upsert(Node(
            node_id="aaaa0001",
            long_name="Tower",
            latitude=40.0,
            longitude=-105.0,
            packet_count=12,
        )))
        _run(self.repo.upsert(Node(
            node_id="bbbb0002",
            long_name="No GPS",
            packet_count=3,
        )))
        self._insert_packet("p1", "aaaa0001", -88.0)
        self._insert_packet("p2", "aaaa0001", -92.0, hours_ago=2)

        data = _run(self.repo.get_coverage_data(hours=168))

        self.assertEqual(data["plotted_count"], 1)
        self.assertEqual(data["unplotted_count"], 1)
        self.assertEqual(data["total_nodes"], 2)
        plotted = data["plotted"][0]
        self.assertEqual(plotted["node_id"], "aaaa0001")
        self.assertEqual(plotted["rssi_quality"], "good")
        self.assertEqual(plotted["recent_packet_count"], 2)
        self.assertAlmostEqual(plotted["avg_rssi"], -90.0, places=1)

    def test_unplotted_count_matches_nodes_without_coordinates(self) -> None:
        now = datetime.now(timezone.utc)
        _run(self.repo.upsert(Node(
            node_id="withgps",
            latitude=39.0,
            longitude=-98.0,
            last_heard=now,
        )))
        _run(self.repo.upsert(Node(
            node_id="nogps1",
            last_heard=now,
        )))
        _run(self.repo.upsert(Node(
            node_id="nogps2",
            latitude=40.0,
            longitude=None,
            last_heard=now,
        )))

        data = _run(self.repo.get_coverage_data())
        self.assertEqual(data["unplotted_count"], 2)
        self.assertEqual(data["plotted_count"], 1)


if __name__ == "__main__":
    unittest.main()
