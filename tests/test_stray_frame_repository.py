from __future__ import annotations

import asyncio
import unittest
from datetime import datetime, timedelta, timezone

from src.models.packet import RawCapture
from src.models.signal import SignalMetrics
from src.storage.database import DatabaseManager
from src.storage.stray_frame_repository import StrayFrameRepository, _peek_channel_hash


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _capture(
    *,
    payload: bytes = b"\x00" * 20,
    rssi: float = -85.0,
    timestamp: datetime | None = None,
) -> RawCapture:
    ts = timestamp or datetime.now(timezone.utc)
    return RawCapture(
        payload=payload,
        signal=SignalMetrics(
            rssi=rssi,
            snr=8.5,
            frequency_mhz=906.875,
            spreading_factor=11,
            bandwidth_khz=250.0,
            timestamp=ts,
        ),
        capture_source="sx1302",
        timestamp=ts,
    )


class TestPeekChannelHash(unittest.TestCase):
    def test_short_payload_returns_none(self) -> None:
        self.assertIsNone(_peek_channel_hash(b"\x00" * 10))

    def test_reads_byte_thirteen_when_header_present(self) -> None:
        payload = bytearray(b"\x00" * 16)
        payload[13] = 0x2A
        self.assertEqual(_peek_channel_hash(bytes(payload)), 0x2A)


class TestStrayFrameRepository(unittest.TestCase):
    def setUp(self) -> None:
        self.db = DatabaseManager(":memory:")
        _run(self.db.connect())
        self.repo = StrayFrameRepository(self.db)

    def tearDown(self) -> None:
        _run(self.db.disconnect())

    def test_insert_and_list_recent(self) -> None:
        payload = bytearray(b"\x00" * 16)
        payload[13] = 7
        _run(self.repo.insert_from_capture(_capture(payload=bytes(payload))))

        frames = _run(self.repo.list_recent(limit=10, hours=24))
        self.assertEqual(len(frames), 1)
        frame = frames[0]
        self.assertEqual(frame.frame_size, 16)
        self.assertEqual(frame.channel_hash, 7)
        self.assertAlmostEqual(frame.frequency_mhz, 906.875)
        self.assertEqual(frame.spreading_factor, 11)
        self.assertAlmostEqual(frame.bandwidth_khz, 250.0)
        self.assertAlmostEqual(frame.rssi, -85.0)
        self.assertAlmostEqual(frame.snr, 8.5)
        self.assertEqual(frame.capture_source, "sx1302")

    def test_list_recent_filters_by_min_rssi(self) -> None:
        _run(self.repo.insert_from_capture(_capture(rssi=-95.0)))
        _run(self.repo.insert_from_capture(_capture(rssi=-70.0)))

        frames = _run(self.repo.list_recent(limit=10, hours=24, min_rssi=-80.0))
        self.assertEqual(len(frames), 1)
        self.assertAlmostEqual(frames[0].rssi, -70.0)

    def test_cleanup_drops_rows_older_than_retention(self) -> None:
        now = datetime.now(timezone.utc)
        old = now - timedelta(hours=200)
        _run(self.repo.insert_from_capture(_capture(timestamp=old)))
        _run(self.repo.insert_from_capture(_capture(timestamp=now)))

        removed = _run(self.repo.cleanup(max_retained=10_000, retention_hours=168))
        self.assertEqual(removed, 1)
        self.assertEqual(_run(self.repo.get_count()), 1)

    def test_cleanup_trims_to_max_retained(self) -> None:
        base = datetime.now(timezone.utc)
        for offset in range(5):
            ts = base + timedelta(seconds=offset)
            _run(self.repo.insert_from_capture(_capture(timestamp=ts)))

        removed = _run(self.repo.cleanup(max_retained=2, retention_hours=0))
        self.assertEqual(removed, 3)
        frames = _run(self.repo.list_recent(limit=10, hours=None))
        self.assertEqual(len(frames), 2)
        self.assertGreater(frames[0].timestamp, frames[1].timestamp)


if __name__ == "__main__":
    unittest.main()
