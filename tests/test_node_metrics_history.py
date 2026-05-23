"""Telemetry and signal history for node drawer charts."""

import unittest
from datetime import datetime, timedelta, timezone

from src.models.telemetry import Telemetry
from src.storage.database import DatabaseManager
from src.storage.packet_repository import PacketRepository
from src.storage.telemetry_repository import TelemetryRepository


class TestNodeMetricsHistory(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = DatabaseManager(":memory:")
        await self.db.connect()
        self.telemetry_repo = TelemetryRepository(self.db)
        self.packet_repo = PacketRepository(self.db)

    async def asyncTearDown(self):
        await self.db.disconnect()

    async def test_telemetry_history_asc_with_hours_filter(self):
        now = datetime.now(timezone.utc)
        for i in range(3):
            await self.telemetry_repo.insert(
                Telemetry(
                    node_id="abc123",
                    battery_level=80 + i,
                    timestamp=now - timedelta(hours=2 - i),
                )
            )

        rows = await self.telemetry_repo.get_history("abc123", limit=50, hours=6)
        self.assertEqual(len(rows), 3)
        self.assertLess(rows[0].timestamp, rows[-1].timestamp)
        self.assertEqual(rows[-1].battery_level, 82)

    async def test_signal_history_from_packets(self):
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
                "p1", "node1", "ffffffff", "meshtastic", "text",
                3, 3, 8, 0, 0, 0, 1, -90.0, 5.0,
                906.875, 11, 250, "concentrator", (now - timedelta(hours=1)).isoformat(),
            ),
        )
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
                "p2", "node1", "ffffffff", "meshtastic", "text",
                3, 3, 8, 0, 0, 0, 1, -85.0, 6.0,
                906.875, 11, 250, "concentrator", now.isoformat(),
            ),
        )
        await self.db.commit()

        signal = await self.packet_repo.get_signal_history("node1", limit=10, hours=24)
        self.assertEqual(len(signal), 2)
        self.assertEqual(signal[0]["rssi"], -90.0)
        self.assertEqual(signal[1]["rssi"], -85.0)


if __name__ == "__main__":
    unittest.main()
