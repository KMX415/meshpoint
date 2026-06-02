"""Tests for ``StaticSource`` and ``UartSource``."""

from __future__ import annotations

import unittest

from src.config import DeviceConfig
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
    """``UartSource`` is a placeholder; surfaces an explanatory error."""

    async def test_status_is_unavailable_with_explanatory_error(self) -> None:
        source = UartSource()
        await source.start()
        try:
            status = source.get_status()
            self.assertEqual(status.source, "uart")
            self.assertFalse(status.available)
            self.assertIsNotNone(status.error)
            # Error must point users to the working alternatives.
            self.assertIn("static", status.error.lower())
            self.assertIn("gpsd", status.error.lower())
        finally:
            await source.stop()

    async def test_source_name_is_stable(self) -> None:
        source = UartSource()
        self.assertEqual(source.source_name, "uart")


if __name__ == "__main__":
    unittest.main()
