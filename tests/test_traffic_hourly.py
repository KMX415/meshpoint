"""Hourly traffic SQL aggregation for the 24h Stats chart."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from src.analytics.toa_estimate import estimate_toa_ms, sum_hourly_toa_ms
from src.storage.database import DatabaseManager
from src.storage.packet_repository import PacketRepository


class TestTrafficHourly(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = DatabaseManager(":memory:")
        await self.db.connect()
        self.repo = PacketRepository(self.db)

    async def asyncTearDown(self):
        await self.db.disconnect()

    async def _insert_packet(
        self,
        packet_id: str,
        protocol: str,
        ts: datetime,
        *,
        sf: int = 11,
        bw: float = 250.0,
        payload: str | None = '{"text":"hi"}',
    ) -> None:
        await self.db.execute(
            """
            INSERT INTO packets (
                packet_id, source_id, destination_id, protocol,
                packet_type, hop_limit, hop_start, channel_hash,
                want_ack, via_mqtt, relay_node, decoded_payload, decrypted,
                rssi, snr, frequency_mhz, spreading_factor,
                bandwidth_khz, capture_source, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                packet_id, "node1", "ffffffff", protocol, "text",
                3, 3, 8, 0, 0, 0, payload, 1,
                -90.0, 5.0, 906.875, sf, bw, "concentrator", ts.isoformat(),
            ),
        )

    async def test_hourly_buckets_split_protocols(self):
        now = datetime.now(timezone.utc).replace(minute=15, second=0, microsecond=0)
        hour_ago = now - timedelta(hours=1)
        two_hours_ago = now - timedelta(hours=2)

        await self._insert_packet("m1", "meshtastic", hour_ago)
        await self._insert_packet("m2", "meshtastic", hour_ago)
        await self._insert_packet("c1", "meshcore", hour_ago)
        await self._insert_packet("old", "meshtastic", two_hours_ago)
        await self.db.commit()

        count_rows, modem_by_hour = await self.repo.get_hourly_traffic(24)
        by_hour = {row["hour_start"]: row for row in count_rows}

        target = hour_ago.strftime("%Y-%m-%dT%H:00:00Z")
        self.assertIn(target, by_hour)
        self.assertEqual(by_hour[target]["meshtastic"], 2)
        self.assertEqual(by_hour[target]["meshcore"], 1)
        self.assertEqual(by_hour[target]["total"], 3)
        self.assertIn(target, modem_by_hour)
        self.assertGreaterEqual(len(modem_by_hour[target]), 1)

    async def test_empty_hours_filled_in_route_shape(self):
        """Route layer fills missing hours; repo returns only non-empty buckets."""
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        await self._insert_packet("only", "meshtastic", now)
        await self.db.commit()

        count_rows, _ = await self.repo.get_hourly_traffic(3)
        self.assertEqual(len(count_rows), 1)
        self.assertEqual(count_rows[0]["total"], 1)

    def test_toa_estimate_positive_for_valid_modem(self):
        ms = estimate_toa_ms(11, 250.0, payload_bytes=40)
        self.assertGreater(ms, 0)

    def test_sum_hourly_toa_ms_aggregates_buckets(self):
        buckets = [
            {"sf": 11, "bw": 250.0, "packet_count": 10, "avg_payload": 40},
            {"sf": 12, "bw": 125.0, "packet_count": 2, "avg_payload": 30},
        ]
        total = sum_hourly_toa_ms(
            buckets,
            default_sf=11,
            default_bw_khz=250.0,
        )
        expected = (
            10 * estimate_toa_ms(11, 250.0, payload_bytes=40)
            + 2 * estimate_toa_ms(12, 125.0, payload_bytes=30)
        )
        self.assertEqual(total, expected)


if __name__ == "__main__":
    unittest.main()
