"""Tests for PositionBroadcaster lifecycle and hot-reload."""

from __future__ import annotations

import asyncio
import unittest

from src.transmit.position_broadcaster import PositionBroadcaster
from src.transmit.tx_service import SendResult


class _FakeTxService:
    def __init__(self, results=None):
        self.calls = 0
        self._results = list(results or [])

    async def send_position(self, lat, lon, alt):
        self.calls += 1
        if self._results:
            return self._results.pop(0)
        return SendResult(
            success=True, packet_id="pos1",
            protocol="meshtastic", airtime_ms=10,
        )


def _ok():
    return SendResult(success=True, packet_id="p", protocol="meshtastic", airtime_ms=5)


class TestPositionBroadcaster(unittest.IsolatedAsyncioTestCase):
    async def test_broadcasts_when_coords_available(self):
        tx = _FakeTxService(results=[_ok()])
        b = PositionBroadcaster(
            tx,
            interval_minutes=10_000,
            startup_delay_seconds=0,
            coords_provider=lambda: (40.0, -74.0, 10.0),
        )
        await b.start()
        await asyncio.sleep(0.05)
        await b.stop()
        self.assertGreaterEqual(tx.calls, 1)

    async def test_hidden_registered_pin_never_calls_transmit(self):
        from src.config import AppConfig
        from src.transmit.mesh_position_resolver import MeshPositionResolver
        from unittest.mock import MagicMock
        config = AppConfig()
        config.device.latitude, config.device.longitude = 40.7128, -74.006
        config.transmit.position.location_precision = "none"
        tx = _FakeTxService()
        broadcaster = PositionBroadcaster(tx, coords_provider=MeshPositionResolver(config, MagicMock()).resolve)
        await broadcaster._broadcast_once()
        self.assertEqual(tx.calls, 0)

    async def test_hidden_after_previous_send_yields_and_can_resume(self):
        from datetime import datetime, timedelta, timezone
        tx = _FakeTxService()
        calls = 0
        broadcaster = None
        def coords():
            nonlocal calls
            calls += 1
            # Bound a regression safely: the broken loop cannot starve the test forever.
            if calls >= 5:
                broadcaster._running = False
            return None
        broadcaster = PositionBroadcaster(tx, startup_delay_seconds=0, coords_provider=coords)
        previous = datetime.now(timezone.utc) - timedelta(minutes=20)
        broadcaster._schedule._last_sent_at = previous
        await broadcaster.start()
        try:
            await asyncio.sleep(0.02)
            self.assertEqual(calls, 1, "Hidden must wait instead of spinning when overdue")
            self.assertEqual(tx.calls, 0)
            self.assertEqual(broadcaster.last_sent_at, previous)
            self.assertGreater(broadcaster.next_due_at, datetime.now(timezone.utc))
            broadcaster._coords_provider = lambda: (40.71, -74.01, None)
            await broadcaster._broadcast_once()
            self.assertEqual(tx.calls, 1)
            self.assertGreater(broadcaster.last_sent_at, previous)
        finally:
            await broadcaster.stop()

    async def test_skips_when_no_coords(self):
        tx = _FakeTxService(results=[_ok()])
        b = PositionBroadcaster(
            tx,
            interval_minutes=10_000,
            startup_delay_seconds=0,
            coords_provider=lambda: None,
        )
        await b.start()
        await asyncio.sleep(0.05)
        await b.stop()
        self.assertEqual(tx.calls, 0)

    async def test_set_interval_zero_pauses(self):
        tx = _FakeTxService(results=[_ok(), _ok()])
        b = PositionBroadcaster(
            tx,
            interval_minutes=10_000,
            startup_delay_seconds=0,
            coords_provider=lambda: (40.0, -74.0, None),
        )
        await b.start()
        await asyncio.sleep(0.05)
        initial = tx.calls
        self.assertGreaterEqual(initial, 1)
        b.set_interval(0)
        await asyncio.sleep(0.05)
        self.assertEqual(tx.calls, initial)
        await b.stop()

    async def test_resume_from_paused_fires(self):
        tx = _FakeTxService(results=[_ok(), _ok()])
        b = PositionBroadcaster(
            tx,
            interval_minutes=0,
            startup_delay_seconds=0,
            coords_provider=lambda: (40.0, -74.0, None),
        )
        await b.start()
        await asyncio.sleep(0.02)
        self.assertEqual(tx.calls, 0)
        b.set_interval(10_000)
        await asyncio.sleep(0.05)
        self.assertGreaterEqual(tx.calls, 1)
        await b.stop()
