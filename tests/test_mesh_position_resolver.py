"""Tests for mesh POSITION coordinate resolution."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from src.config import AppConfig, LocationConfig, PositionConfig
from src.hal.location import GpsStatus, LocationFix, LocationSource
from src.transmit.mesh_position_resolver import MeshPositionResolver


class TestMeshPositionResolver(unittest.TestCase):
    def _resolver(
        self,
        *,
        mesh_source: str = "static",
        mesh_precision: str = "approximate",
        location_source: str = "static",
        device_lat: float | None = 40.7128,
        device_lon: float | None = -74.0060,
        fix: LocationFix | None = None,
    ) -> MeshPositionResolver:
        cfg = AppConfig()
        cfg.device.latitude = device_lat
        cfg.device.longitude = device_lon
        cfg.device.altitude = 25.0
        cfg.location = LocationConfig(source=location_source)
        cfg.transmit.position = PositionConfig(
            coordinate_source=mesh_source,
            location_precision=mesh_precision,
        )

        fake = MagicMock(spec=LocationSource)
        fake.source_name = location_source
        if fix is None and location_source != "static":
            fix = LocationFix(mode=3, latitude=40.8000, longitude=-73.9000, altitude_m=15.0)
        fake.get_status.return_value = GpsStatus(
            source=location_source,
            available=True,
            fix=fix,
        )
        return MeshPositionResolver(cfg, fake)

    def test_static_mesh_uses_registered_pin_exact(self) -> None:
        result = self._resolver(mesh_source="static").resolve()
        self.assertEqual(result, (40.7128, -74.0060, 25.0))

    def test_live_mesh_uses_gps_fix_with_approximate_privacy(self) -> None:
        resolver = self._resolver(
            mesh_source="live",
            mesh_precision="approximate",
            location_source="gpsd",
        )
        self.assertEqual(resolver.resolve(), (40.8, -73.9, 15.0))

    def test_live_mesh_exact_preserves_precision(self) -> None:
        resolver = self._resolver(
            mesh_source="live",
            mesh_precision="exact",
            location_source="gpsd",
        )
        self.assertEqual(resolver.resolve(), (40.8, -73.9, 15.0))

    def test_live_mesh_none_skips_broadcast(self) -> None:
        resolver = self._resolver(
            mesh_source="live",
            mesh_precision="none",
            location_source="gpsd",
        )
        self.assertIsNone(resolver.resolve())

    def test_live_mesh_requires_live_location_source(self) -> None:
        resolver = self._resolver(mesh_source="live", location_source="static")
        self.assertIsNone(resolver.resolve())

    def test_static_mesh_missing_coordinates(self) -> None:
        resolver = self._resolver(
            mesh_source="static",
            device_lat=None,
            device_lon=None,
        )
        self.assertIsNone(resolver.resolve())


if __name__ == "__main__":
    unittest.main()
