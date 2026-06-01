"""Tests for ``PipelineCoordinator``'s ``LocationSource`` integration."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock

from src.config import AppConfig, LocationConfig
from src.coordinator import PipelineCoordinator
from src.hal.location import (
    GpsStatus,
    LocationFix,
    LocationSource,
    StaticSource,
)


class TestCoordinatorBuildsLocationSource(unittest.TestCase):
    """Coordinator constructs a ``LocationSource`` from config at __init__."""

    def test_default_config_yields_static_source(self) -> None:
        cfg = AppConfig()
        coord = PipelineCoordinator(cfg)
        self.assertIsInstance(coord.location_source, LocationSource)
        self.assertEqual(coord.location_source.source_name, "static")
        self.assertIsInstance(coord.location_source, StaticSource)

    def test_gpsd_config_yields_gpsd_source(self) -> None:
        cfg = AppConfig()
        cfg.location = LocationConfig(source="gpsd")
        coord = PipelineCoordinator(cfg)
        self.assertEqual(coord.location_source.source_name, "gpsd")

    def test_uart_config_yields_uart_source(self) -> None:
        cfg = AppConfig()
        cfg.location = LocationConfig(source="uart")
        coord = PipelineCoordinator(cfg)
        self.assertEqual(coord.location_source.source_name, "uart")


class TestApplyLatestLocationFix(unittest.TestCase):
    """Live fixes notify listeners but do not overwrite ``device.*``."""

    def _coord_with_fake_source(
        self,
        status: GpsStatus,
        *,
        source_name: str = "gpsd",
    ) -> PipelineCoordinator:
        cfg = AppConfig()
        cfg.device.latitude = 40.0
        cfg.device.longitude = -74.0
        cfg.device.altitude = 99.0
        coord = PipelineCoordinator(cfg)
        fake = MagicMock(spec=LocationSource)
        fake.get_status.return_value = status
        fake.source_name = source_name
        coord._location_source = fake  # noqa: SLF001
        return coord

    def test_live_fix_does_not_overwrite_registered_device_coordinates(self) -> None:
        status = GpsStatus(
            source="gpsd",
            available=True,
            fix=LocationFix(
                mode=3, latitude=40.7128, longitude=-74.0060, altitude_m=12.3,
            ),
            last_update=datetime.now(timezone.utc),
        )
        coord = self._coord_with_fake_source(status)
        coord._apply_latest_location_fix()  # noqa: SLF001

        self.assertEqual(coord._config.device.latitude, 40.0)  # noqa: SLF001
        self.assertEqual(coord._config.device.longitude, -74.0)  # noqa: SLF001
        self.assertEqual(coord._config.device.altitude, 99.0)  # noqa: SLF001

    def test_static_source_is_a_no_op(self) -> None:
        status = GpsStatus(
            source="static",
            available=True,
            fix=LocationFix(mode=3, latitude=41.0, longitude=-73.0, altitude_m=5.0),
        )
        coord = self._coord_with_fake_source(status, source_name="static")
        seen: list[tuple] = []
        coord.on_location_update(lambda lat, lon, alt: seen.append((lat, lon, alt)))
        coord._apply_latest_location_fix()  # noqa: SLF001

        self.assertEqual(seen, [])

    def test_unavailable_source_does_not_notify(self) -> None:
        status = GpsStatus(
            source="gpsd",
            available=False,
            error="Connection refused",
        )
        coord = self._coord_with_fake_source(status)
        seen: list[tuple] = []
        coord.on_location_update(lambda lat, lon, alt: seen.append((lat, lon, alt)))
        coord._apply_latest_location_fix()  # noqa: SLF001

        self.assertEqual(seen, [])

    def test_no_fix_does_not_notify(self) -> None:
        status = GpsStatus(
            source="gpsd",
            available=True,
            fix=LocationFix(mode=1, latitude=None, longitude=None, altitude_m=None),
        )
        coord = self._coord_with_fake_source(status)
        seen: list[tuple] = []
        coord.on_location_update(lambda lat, lon, alt: seen.append((lat, lon, alt)))
        coord._apply_latest_location_fix()  # noqa: SLF001

        self.assertEqual(seen, [])

    def test_unchanged_live_fix_is_a_no_op(self) -> None:
        status = GpsStatus(
            source="gpsd",
            available=True,
            fix=LocationFix(mode=3, latitude=40.0, longitude=-74.0, altitude_m=10.0),
        )
        coord = self._coord_with_fake_source(status)
        seen: list[tuple] = []
        coord.on_location_update(lambda lat, lon, alt: seen.append((lat, lon, alt)))

        coord._apply_latest_location_fix()  # noqa: SLF001
        coord._apply_latest_location_fix()  # noqa: SLF001

        self.assertEqual(len(seen), 1)


class TestLocationUpdateCallback(unittest.TestCase):
    """``on_location_update`` listeners fire on live fix changes only."""

    def _coord_with_fake_source(self, status: GpsStatus) -> PipelineCoordinator:
        cfg = AppConfig()
        coord = PipelineCoordinator(cfg)
        fake = MagicMock(spec=LocationSource)
        fake.get_status.return_value = status
        fake.source_name = "gpsd"
        coord._location_source = fake  # noqa: SLF001
        return coord

    def test_callback_fires_on_first_real_fix(self) -> None:
        status = GpsStatus(
            source="gpsd",
            available=True,
            fix=LocationFix(mode=3, latitude=40.0, longitude=-74.0, altitude_m=10.0),
        )
        coord = self._coord_with_fake_source(status)
        seen: list[tuple] = []
        coord.on_location_update(lambda lat, lon, alt: seen.append((lat, lon, alt)))

        coord._apply_latest_location_fix()  # noqa: SLF001

        self.assertEqual(seen, [(40.0, -74.0, 10.0)])

    def test_callback_exception_does_not_break_others(self) -> None:
        status = GpsStatus(
            source="gpsd",
            available=True,
            fix=LocationFix(mode=3, latitude=40.0, longitude=-74.0, altitude_m=10.0),
        )
        coord = self._coord_with_fake_source(status)
        good_calls: list[tuple] = []

        def boom(lat, lon, alt):
            raise RuntimeError("listener went rogue")

        coord.on_location_update(boom)
        coord.on_location_update(
            lambda lat, lon, alt: good_calls.append((lat, lon, alt))
        )
        coord._apply_latest_location_fix()  # noqa: SLF001

        self.assertEqual(good_calls, [(40.0, -74.0, 10.0)])


if __name__ == "__main__":
    unittest.main()
