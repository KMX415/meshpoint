"""Tests for ``build_location_source``: routes config to right concrete source."""

from __future__ import annotations

import unittest

from src.config import DeviceConfig, LocationConfig
from src.hal.location.factory import build_location_source
from src.hal.location.gpsd_source import GpsdSource
from src.hal.location.static_source import StaticSource
from src.hal.location.uart_source import UartSource


class TestBuildLocationSource(unittest.TestCase):
    """``build_location_source`` returns the source matching ``LocationConfig.source``."""

    def test_default_config_returns_static(self) -> None:
        source = build_location_source(LocationConfig(), DeviceConfig())
        self.assertIsInstance(source, StaticSource)
        self.assertEqual(source.source_name, "static")

    def test_explicit_static(self) -> None:
        source = build_location_source(
            LocationConfig(source="static"), DeviceConfig()
        )
        self.assertIsInstance(source, StaticSource)

    def test_gpsd_passes_host_and_port(self) -> None:
        cfg = LocationConfig(
            source="gpsd",
            gpsd_host="192.168.0.50",
            gpsd_port=2948,
            min_fix_quality=2,
        )
        source = build_location_source(cfg, DeviceConfig())
        self.assertIsInstance(source, GpsdSource)
        self.assertEqual(source.source_name, "gpsd")
        # Internal connection params reach the source so reconnect uses them.
        self.assertEqual(source._host, "192.168.0.50")  # noqa: SLF001
        self.assertEqual(source._port, 2948)  # noqa: SLF001
        self.assertEqual(source._min_fix_quality, 2)  # noqa: SLF001

    def test_uart(self) -> None:
        source = build_location_source(
            LocationConfig(source="uart"), DeviceConfig()
        )
        self.assertIsInstance(source, UartSource)

    def test_unknown_source_falls_back_to_static(self) -> None:
        # Forward-compat: a ``local.yaml`` from a future Meshpoint
        # version must not brick boot on an old runtime.
        source = build_location_source(
            LocationConfig(source="quantum-entangled"), DeviceConfig()
        )
        self.assertIsInstance(source, StaticSource)

    def test_case_insensitive_source(self) -> None:
        source = build_location_source(
            LocationConfig(source="GPSD"), DeviceConfig()
        )
        self.assertIsInstance(source, GpsdSource)

    def test_empty_string_falls_back_to_static(self) -> None:
        source = build_location_source(
            LocationConfig(source=""), DeviceConfig()
        )
        self.assertIsInstance(source, StaticSource)


if __name__ == "__main__":
    unittest.main()
