"""Tests for ``StaticSource`` and ``UartSource``."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.config import DeviceConfig
from src.hal.gps_reader import GpsPosition
from src.hal.location.static_source import StaticSource
from src.hal.location.uart_source import UartSource


class TestStaticSource(unittest.IsolatedAsyncioTestCase):
    """``StaticSource`` reports configured device coords as a fixed 3D fix."""

    async def test_valid_coordinates_yield_3d_fix(self) -> None:
        device = DeviceConfig(latitude=40.7128, longitude=-74.0060, altitude=12.0)
        source = StaticSource(device)
        await source.start()
        try:
            status = source.get_status()
            self.assertEqual(status.source, "static")
            self.assertTrue(status.available)
            self.assertEqual(status.fix.mode, 3)
            self.assertEqual(status.fix.mode_label, "3D")
            self.assertEqual(status.fix.latitude, 40.7128)
            self.assertEqual(status.fix.longitude, -74.0060)
            self.assertEqual(status.fix.altitude_m, 12.0)
            self.assertIsNone(status.satellites)
            self.assertIsNone(status.device)
        finally:
            await source.stop()

    async def test_missing_coordinates_yield_unavailable(self) -> None:
        device = DeviceConfig(latitude=None, longitude=None, altitude=None)
        source = StaticSource(device)
        await source.start()
        status = source.get_status()
        self.assertFalse(status.available)
        self.assertIsNone(status.fix)
        self.assertEqual(status.error, "No coordinates configured")

    async def test_partial_coordinates_yield_unavailable(self) -> None:
        # Lat without lon -- uncommon but possible mid-edit. Don't drop
        # a pin at (40, 0) silently.
        device = DeviceConfig(latitude=40.0, longitude=None)
        source = StaticSource(device)
        await source.start()
        status = source.get_status()
        self.assertFalse(status.available)

    async def test_out_of_range_coordinates_treated_as_invalid(self) -> None:
        device = DeviceConfig(latitude=200.0, longitude=400.0)
        source = StaticSource(device)
        await source.start()
        status = source.get_status()
        self.assertFalse(status.available)

    async def test_start_is_idempotent(self) -> None:
        device = DeviceConfig(latitude=40.0, longitude=-74.0)
        source = StaticSource(device)
        await source.start()
        await source.start()  # must not raise

    async def test_stop_is_idempotent(self) -> None:
        device = DeviceConfig(latitude=40.0, longitude=-74.0)
        source = StaticSource(device)
        await source.stop()  # without prior start
        await source.start()
        await source.stop()
        await source.stop()  # second stop is a no-op

    async def test_source_name_is_stable(self) -> None:
        source = StaticSource(DeviceConfig())
        self.assertEqual(source.source_name, "static")


class TestUartSource(unittest.IsolatedAsyncioTestCase):
    """``UartSource`` exposes live NMEA fixes via ``GpsReader``."""

    async def test_status_before_start_is_unavailable(self) -> None:
        source = UartSource()
        status = source.get_status()
        self.assertEqual(status.source, "uart")
        self.assertFalse(status.available)
        self.assertIn("not started", (status.error or "").lower())

    async def test_status_with_fix(self) -> None:
        source = UartSource()
        source._reader = MagicMock()
        source._started = True
        source._reader.latest_position = GpsPosition(
            latitude=51.5,
            longitude=-0.1,
            altitude=20.0,
            satellites=6,
            fix_quality=2,
            timestamp=datetime(2026, 6, 2, tzinfo=timezone.utc),
        )
        status = source.get_status()
        self.assertTrue(status.available)
        self.assertIsNotNone(status.fix)
        self.assertEqual(status.device.path, "/dev/ttyAMA0")

    async def test_source_name_is_stable(self) -> None:
        source = UartSource()
        self.assertEqual(source.source_name, "uart")


if __name__ == "__main__":
    unittest.main()
