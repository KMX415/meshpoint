"""Telemetry row-count retention (mirrors packet cleanup).

Credit: javastraat/meshpoint ``691dcd5``.
"""

from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta, timezone

from src.models.telemetry import Telemetry
from src.storage.database import DatabaseManager
from src.storage.telemetry_repository import TelemetryRepository


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TelemetryCleanupTest(unittest.TestCase):
    def setUp(self):
        self.db = DatabaseManager(":memory:")
        _run(self.db.connect())
        self.repo = TelemetryRepository(self.db)

    def tearDown(self):
        _run(self.db.disconnect())

    async def _seed(self, count: int) -> None:
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for i in range(count):
            await self.repo.insert(
                Telemetry(
                    node_id="aabbccdd",
                    battery_level=50.0,
                    voltage=3.7,
                    temperature=20.0 + i,
                    humidity=None,
                    barometric_pressure=None,
                    channel_utilization=None,
                    air_util_tx=None,
                    uptime_seconds=i,
                    timestamp=base + timedelta(minutes=i),
                )
            )

    def test_cleanup_noop_when_under_cap(self):
        _run(self._seed(3))
        removed = _run(self.repo.cleanup_old(10))
        self.assertEqual(removed, 0)
        self.assertEqual(_run(self.repo.get_count()), 3)

    def test_cleanup_prunes_oldest_first(self):
        _run(self._seed(5))
        removed = _run(self.repo.cleanup_old(2))
        self.assertEqual(removed, 3)
        self.assertEqual(_run(self.repo.get_count()), 2)
        history = _run(self.repo.get_history("aabbccdd", limit=10))
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0].uptime_seconds, 3)
        self.assertEqual(history[1].uptime_seconds, 4)


if __name__ == "__main__":
    unittest.main()
