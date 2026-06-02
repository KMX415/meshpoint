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
    """``_apply_latest_location_fix`` writes live fixes back to ``device``."""

    def _coord_with_fake_source(self, status: GpsStatus) -> PipelineCoordinator:
        cfg = AppConfig()
        cfg.device.latitude = None
        cfg.device.longitude = None
        cfg.device.altitude = None
        coord = PipelineCoordinator(cfg)
        # Replace the constructor-built static source with a fake whose
        # ``get_status`` returns the supplied snapshot.
        fake = MagicMock(spec=LocationSource)
        fake.get_status.return_value = status
        fake.source_name = "test-fake"
        coord._location_source = fake  # noqa: SLF001
        return coord

    def test_3d_fix_overwrites_device_coordinates(self) -> None:
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

        self.assertAlmostEqual(coord._config.device.latitude, 40.7128)  # noqa: SLF001
        self.assertAlmostEqual(coord._config.device.longitude, -74.0060)  # noqa: SLF001
        self.assertAlmostEqual(coord._config.device.altitude, 12.3)  # noqa: SLF001

    def test_2d_fix_keeps_existing_altitude(self) -> None:
        status = GpsStatus(
            source="gpsd",
            available=True,
            fix=LocationFix(
                mode=2, latitude=40.0, longitude=-74.0, altitude_m=None,
            ),
        )
        coord = self._coord_with_fake_source(status)
        coord._config.device.altitude = 99.0  # noqa: SLF001
        coord._apply_latest_location_fix()  # noqa: SLF001

        self.assertEqual(coord._config.device.altitude, 99.0)  # noqa: SLF001

    def test_unavailable_source_does_not_overwrite_device(self) -> None:
        status = GpsStatus(
            source="gpsd",
            available=False,
            error="Connection refused",
        )
        coord = self._coord_with_fake_source(status)
        coord._config.device.latitude = 40.0  # noqa: SLF001
        coord._config.device.longitude = -74.0  # noqa: SLF001

        coord._apply_latest_location_fix()  # noqa: SLF001

        # Stale fallback coordinates preserved.
        self.assertEqual(coord._config.device.latitude, 40.0)  # noqa: SLF001
        self.assertEqual(coord._config.device.longitude, -74.0)  # noqa: SLF001

    def test_no_fix_does_not_overwrite_device(self) -> None:
        status = GpsStatus(
            source="gpsd",
            available=True,
            fix=LocationFix(mode=1, latitude=None, longitude=None, altitude_m=None),
        )
        coord = self._coord_with_fake_source(status)
        coord._config.device.latitude = 40.0  # noqa: SLF001
        coord._config.device.longitude = -74.0  # noqa: SLF001

        coord._apply_latest_location_fix()  # noqa: SLF001

        self.assertEqual(coord._config.device.latitude, 40.0)  # noqa: SLF001
        self.assertEqual(coord._config.device.longitude, -74.0)  # noqa: SLF001

    def test_unchanged_position_is_a_no_op(self) -> None:
        # Same coords flowing through every tick must not constantly
        # re-write the device fields (avoids unnecessary churn for
        # callers that watch the values).
        status = GpsStatus(
            source="gpsd",
            available=True,
            fix=LocationFix(mode=3, latitude=40.0, longitude=-74.0, altitude_m=10.0),
        )
        coord = self._coord_with_fake_source(status)
        coord._apply_latest_location_fix()  # noqa: SLF001
        first_lat = coord._config.device.latitude  # noqa: SLF001
        coord._apply_latest_location_fix()  # noqa: SLF001

        self.assertEqual(coord._config.device.latitude, first_lat)  # noqa: SLF001


class TestLocationUpdateCallback(unittest.TestCase):
    """``on_location_update`` listeners fire on real position changes only.

    The callback is the bridge that keeps ``DeviceIdentity`` (used by the
    ``/api/device`` endpoint and the upstream Meshradar registration
    payload) in sync with the live GPS source.
    """

    def _coord_with_fake_source(self, status: GpsStatus) -> PipelineCoordinator:
        cfg = AppConfig()
        cfg.device.latitude = None
        cfg.device.longitude = None
        cfg.device.altitude = None
        coord = PipelineCoordinator(cfg)
        fake = MagicMock(spec=LocationSource)
        fake.get_status.return_value = status
        fake.source_name = "test-fake"
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

    def test_callback_does_not_fire_when_position_unchanged(self) -> None:
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
