"""Unit tests for history time-bucket width helper.

Credit: javastraat/meshpoint ``b10610a``.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from src.models.telemetry import Telemetry
from src.storage.database import DatabaseManager
from src.storage.telemetry_repository import TelemetryRepository
from src.storage.time_bucket import bucket_seconds


class BucketSecondsTest(unittest.TestCase):
    def test_uses_actual_span_not_requested_hours(self):
        lo = datetime(2026, 1, 1, tzinfo=timezone.utc)
        hi = lo + timedelta(hours=2)
        secs = bucket_seconds(
            {"lo": lo.isoformat(), "hi": hi.isoformat()},
            limit=10,
            hours=100000,
        )
        self.assertEqual(secs, max(60, int((2 * 3600) / 10)))

    def test_falls_back_to_hours_when_no_span(self):
        self.assertEqual(bucket_seconds(None, limit=10, hours=1), 360)

    def test_floor_at_sixty_seconds(self):
        lo = datetime(2026, 1, 1, tzinfo=timezone.utc)
        hi = lo + timedelta(seconds=30)
        self.assertEqual(
            bucket_seconds(
                {"lo": lo.isoformat(), "hi": hi.isoformat()},
                limit=100,
                hours=1,
            ),
            60,
        )


class TelemetryHistoryBucketTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = DatabaseManager(":memory:")
        await self.db.connect()
        self.repo = TelemetryRepository(self.db)

    async def asyncTearDown(self):
        await self.db.disconnect()

    async def test_hours_path_keeps_newest_when_over_limit(self):
        now = datetime.now(timezone.utc)
        for i in range(20):
            await self.repo.insert(
                Telemetry(
                    node_id="n1",
                    temperature=float(i),
                    timestamp=now - timedelta(minutes=19 - i),
                )
            )
        rows = await self.repo.get_history("n1", limit=5, hours=24)
        self.assertLessEqual(len(rows), 5)
        self.assertGreaterEqual(rows[-1].temperature, 15.0)


if __name__ == "__main__":
    unittest.main()
