"""Tests for ``UartSource`` and UART-related config defaults."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from src.config import AppConfig, LocationConfig
from src.hal.gps_reader import GpsPosition
from src.hal.location.factory import build_location_source
from src.hal.location.uart_source import UartSource


class TestLocationConfigUartDefaults(unittest.TestCase):
    def test_uart_path_defaults_to_ttyama0(self) -> None:
        cfg = LocationConfig()
        self.assertEqual(cfg.uart_path, "/dev/ttyAMA0")

    def test_uart_baud_defaults_to_9600(self) -> None:
        cfg = LocationConfig()
        self.assertEqual(cfg.uart_baud, 9600)


class TestUartSource(unittest.IsolatedAsyncioTestCase):
    async def test_no_fix_yet_is_available_without_error(self) -> None:
        source = UartSource()
        source._reader = MagicMock()
        source._reader.latest_position = None
        source._started = True

        status = source.get_status()
        self.assertEqual(status.source, "uart")
        self.assertTrue(status.available)
        self.assertIsNone(status.fix)

    async def test_maps_gga_position_to_location_fix(self) -> None:
        source = UartSource(min_fix_quality=1)
        source._reader = MagicMock()
        source._started = True
        source._reader.latest_position = GpsPosition(
            latitude=40.7128,
            longitude=-74.0060,
            altitude=12.0,
            satellites=8,
            fix_quality=1,
            timestamp=datetime(2026, 6, 2, 12, 0, 0, tzinfo=timezone.utc),
        )

        status = source.get_status()
        self.assertTrue(status.available)
        self.assertIsNotNone(status.fix)
        assert status.fix is not None
        self.assertEqual(status.fix.latitude, 40.7128)
        self.assertEqual(status.fix.longitude, -74.0060)
        self.assertEqual(status.fix.altitude_m, 12.0)
        self.assertIsNotNone(status.satellites)
        assert status.satellites is not None
        self.assertEqual(status.satellites.used, 8)

    async def test_min_fix_quality_filters_weak_gga(self) -> None:
        source = UartSource(min_fix_quality=2)
        source._reader = MagicMock()
        source._started = True
        source._reader.latest_position = GpsPosition(
            latitude=40.0,
            longitude=-74.0,
            altitude=0.0,
            satellites=4,
            fix_quality=1,
            timestamp=datetime.now(timezone.utc),
        )

        status = source.get_status()
        self.assertTrue(status.available)
        self.assertIsNone(status.fix)

    async def test_start_stop_wires_gps_reader(self) -> None:
        source = UartSource(uart_path="/dev/ttyAMA0", baud=9600)
        with patch("src.hal.location.uart_source.GpsReader") as reader_cls:
            reader = MagicMock()
            reader.start = AsyncMock()
            reader.stop = AsyncMock()
            reader_cls.return_value = reader

            await source.start()
            reader_cls.assert_called_once_with(
                uart_path="/dev/ttyAMA0", baud=9600
            )
            reader.start.assert_awaited_once()

            await source.stop()
            reader.stop.assert_awaited_once()


class TestUartFactory(unittest.TestCase):
    def test_build_uart_source_from_config(self) -> None:
        app = AppConfig()
        app.location.source = "uart"
        app.location.uart_path = "/dev/serial0"
        app.location.uart_baud = 115200

        source = build_location_source(app.location, app.device)
        self.assertIsInstance(source, UartSource)
        self.assertEqual(source._uart_path, "/dev/serial0")
        self.assertEqual(source._baud, 115200)


if __name__ == "__main__":
    unittest.main()
