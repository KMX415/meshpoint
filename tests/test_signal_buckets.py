"""Signal bucket aggregation for node-card sparklines."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from src.storage.database import DatabaseManager
from src.storage.packet_repository import PacketRepository


class TestSignalBuckets(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = DatabaseManager(":memory:")
        await self.db.connect()
        self.repo = PacketRepository(self.db)

    async def asyncTearDown(self):
        await self.db.disconnect()

    async def _insert_signal(
        self,
        packet_id: str,
        rssi: float,
        ts: datetime,
        *,
        source_id: str = "node1",
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO packets (
                packet_id, source_id, destination_id, protocol,
                packet_type, hop_limit, hop_start, channel_hash,
                want_ack, via_mqtt, relay_node, decrypted,
                rssi, snr, frequency_mhz, spreading_factor,
                bandwidth_khz, capture_source, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                packet_id, source_id, "ffffffff", "meshtastic", "text",
                3, 3, 8, 0, 0, 0, 1, rssi, 5.0,
                906.875, 11, 250, "concentrator", ts.isoformat(),
            ),
        )

    async def test_buckets_aggregate_by_15_minutes(self):
        base = datetime.now(timezone.utc).replace(
            minute=10, second=0, microsecond=0,
        )
        await self._insert_signal("a", -95.0, base)
        await self._insert_signal("b", -85.0, base + timedelta(minutes=2))
        await self._insert_signal("c", -105.0, base + timedelta(minutes=8))
        await self.db.commit()

        buckets = await self.repo.get_signal_buckets(
            "node1", hours=24, bucket_minutes=15,
        )
        self.assertEqual(len(buckets), 2)

        first_key = base.replace(minute=0).strftime("%Y-%m-%dT%H:00:00+00:00")
        second_key = base.replace(minute=15).strftime("%Y-%m-%dT%H:15:00+00:00")
        by_bucket = {b["bucket"]: b for b in buckets}

        self.assertEqual(by_bucket[first_key]["packet_count"], 2)
        self.assertAlmostEqual(by_bucket[first_key]["rssi_avg"], -90.0)
        self.assertEqual(by_bucket[second_key]["packet_count"], 1)
        self.assertAlmostEqual(by_bucket[second_key]["rssi_avg"], -105.0)

    async def test_buckets_ignore_other_nodes(self):
        now = datetime.now(timezone.utc)
        await self._insert_signal("mine", -88.0, now, source_id="node1")
        await self._insert_signal("other", -70.0, now, source_id="node2")
        await self.db.commit()

        buckets = await self.repo.get_signal_buckets("node1", hours=1)
        self.assertEqual(len(buckets), 1)
        self.assertAlmostEqual(buckets[0]["rssi_avg"], -88.0)

    async def test_buckets_skip_null_rssi(self):
        now = datetime.now(timezone.utc)
        await self.db.execute(
            """
            INSERT INTO packets (
                packet_id, source_id, destination_id, protocol,
                packet_type, hop_limit, hop_start, channel_hash,
                want_ack, via_mqtt, relay_node, decrypted,
                rssi, snr, frequency_mhz, spreading_factor,
                bandwidth_khz, capture_source, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "null", "node1", "ffffffff", "meshtastic", "text",
                3, 3, 8, 0, 0, 0, 1, None, None,
                906.875, 11, 250, "concentrator", now.isoformat(),
            ),
        )
        await self.db.commit()

        buckets = await self.repo.get_signal_buckets("node1", hours=1)
        self.assertEqual(buckets, [])


if __name__ == "__main__":
    unittest.main()
