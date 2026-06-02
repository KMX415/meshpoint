"""Tests for ``GET /api/device/gps-status`` and the extended ``PUT /api/config/gps``."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import device_config_routes, gps_status
from src.config import AppConfig
from src.hal.location import (
    GpsDeviceInfo,
    GpsStatus,
    LocationFix,
    LocationSource,
    Satellite,
    SatellitesView,
)


def _bypass_admin_auth(monkey_app: FastAPI) -> None:
    """Override the ``require_admin`` dependency for the route under test."""
    from src.api.auth.dependencies import require_admin
    from src.api.auth.jwt_session import SessionClaims

    def _admin_claims() -> SessionClaims:
        return SessionClaims(subject="test-admin", role="admin", session_version=1)

    monkey_app.dependency_overrides[require_admin] = _admin_claims


def _bypass_audit(monkey_app: FastAPI) -> None:
    from src.api.audit.dependencies import get_audit_writer

    audit = MagicMock()

    class _Ctx:
        def __enter__(self):  # noqa: D401
            return self

        def __exit__(self, *args, **kwargs):
            return False

    audit.timed_action.return_value = _Ctx()
    monkey_app.dependency_overrides[get_audit_writer] = lambda: audit


class _SimpleSession:
    """SessionClaims-like object that satisfies ``require_admin``."""

    subject = "test-admin"
    role = "admin"
    session_version = 1


class TestGpsStatusEndpoint(unittest.TestCase):
    """``GET /api/device/gps-status`` mirrors the active source's snapshot."""

    def setUp(self) -> None:
        self.app = FastAPI()
        self.app.include_router(gps_status.router)

        self.fake_source = MagicMock(spec=LocationSource)
        self.fake_source.source_name = "gpsd"
        gps_status.init_routes(self.fake_source)

        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        gps_status.reset_routes()

    def test_returns_full_payload_with_satellites(self) -> None:
        when = datetime(2026, 5, 30, 16, 37, 1, tzinfo=timezone.utc)
        self.fake_source.get_status.return_value = GpsStatus(
            source="gpsd",
            available=True,
            fix=LocationFix(
                mode=3, latitude=40.7128, longitude=-74.0060, altitude_m=12.3,
                hdop=0.9, pdop=1.4, vdop=1.1, time=when,
            ),
            satellites=SatellitesView.from_satellites([
                Satellite(prn=5, azimuth=150.5, elevation=65.0,
                          snr_dbhz=42.0, used=True, gnss="GPS"),
                Satellite(prn=22, azimuth=80.0, elevation=10.0,
                          snr_dbhz=18.0, used=False, gnss="GLONASS"),
            ]),
            device=GpsDeviceInfo(
                driver="u-blox", path="/dev/ttyACM0", model="u-blox 8",
            ),
            last_update=when,
        )

        response = self.client.get("/api/device/gps-status")
        self.assertEqual(response.status_code, 200)

        body = response.json()
        self.assertEqual(body["source"], "gpsd")
        self.assertTrue(body["available"])
        self.assertEqual(body["fix"]["mode_label"], "3D")
        self.assertEqual(body["fix"]["hdop"], 0.9)
        self.assertEqual(body["satellites"]["in_view"], 2)
        self.assertEqual(body["satellites"]["used"], 1)
        # Skyplot data: az/el/snr/gnss for every satellite
        sat = body["satellites"]["list"][0]
        self.assertEqual(sat["azimuth"], 150.5)
        self.assertEqual(sat["elevation"], 65.0)
        self.assertEqual(sat["snr_dbhz"], 42.0)
        self.assertEqual(sat["gnss"], "GPS")
        self.assertEqual(body["device"]["model"], "u-blox 8")

    def test_static_source_returns_no_satellites(self) -> None:
        self.fake_source.get_status.return_value = GpsStatus(
            source="static",
            available=True,
            fix=LocationFix(mode=3, latitude=40.0, longitude=-74.0, altitude_m=10.0),
        )

        response = self.client.get("/api/device/gps-status")
        body = response.json()
        self.assertEqual(body["source"], "static")
        self.assertIsNone(body["satellites"])
        self.assertIsNone(body["device"])

    def test_unavailable_source_includes_error(self) -> None:
        self.fake_source.get_status.return_value = GpsStatus(
            source="gpsd",
            available=False,
            error="Connection refused on 127.0.0.1:2947",
        )

        response = self.client.get("/api/device/gps-status")
        body = response.json()
        self.assertFalse(body["available"])
        self.assertEqual(body["error"], "Connection refused on 127.0.0.1:2947")

    def test_uninitialized_source_returns_503(self) -> None:
        gps_status.reset_routes()
        response = self.client.get("/api/device/gps-status")
        self.assertEqual(response.status_code, 503)


class TestUpdateGpsRoute(unittest.TestCase):
    """``PUT /api/config/gps`` accepts static / gpsd / uart sources."""

    def setUp(self) -> None:
        self.app = FastAPI()
        self.app.include_router(device_config_routes.router)
        _bypass_admin_auth(self.app)
        _bypass_audit(self.app)

        self.config = AppConfig()
        device_config_routes.init_routes(self.config)

        self.client = TestClient(self.app)
        self._patcher = patch(
            "src.api.routes.device_config_routes.save_section_to_yaml",
            new=MagicMock(),
        )
        self._save_mock = self._patcher.start()

    def tearDown(self) -> None:
        device_config_routes.reset_routes()
        self._patcher.stop()

    def test_static_source_persists_coordinates(self) -> None:
        response = self.client.put(
            "/api/config/gps",
            json={
                "source": "static",
                "latitude": 40.7128,
                "longitude": -74.0060,
                "altitude": 12.3,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["saved"])
        self.assertEqual(body["gps"]["source"], "static")
        self.assertEqual(self.config.device.latitude, 40.7128)
        self.assertEqual(self.config.device.longitude, -74.0060)

    def test_static_source_requires_lat_and_lon(self) -> None:
        response = self.client.put(
            "/api/config/gps",
            json={"source": "static", "latitude": 40.0},
        )
        self.assertEqual(response.status_code, 400)

    def test_gpsd_source_persists_connection_details(self) -> None:
        response = self.client.put(
            "/api/config/gps",
            json={
                "source": "gpsd",
                "gpsd_host": "192.168.0.50",
                "gpsd_port": 2948,
                "update_interval_seconds": 2,
                "min_fix_quality": 2,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["saved"])
        # Source change requires service restart for new LocationSource.
        self.assertTrue(body["restart_required"])
        self.assertEqual(body["gps"]["source"], "gpsd")
        self.assertEqual(body["gps"]["gpsd_host"], "192.168.0.50")
        self.assertEqual(body["gps"]["gpsd_port"], 2948)
        self.assertEqual(self.config.location.source, "gpsd")
        self.assertEqual(self.config.location.gpsd_host, "192.168.0.50")
        self.assertEqual(self.config.location.gpsd_port, 2948)

    def test_unchanged_source_does_not_require_restart(self) -> None:
        # Pre-existing static source. Just editing coordinates.
        self.config.location.source = "static"
        response = self.client.put(
            "/api/config/gps",
            json={
                "source": "static",
                "latitude": 41.0,
                "longitude": -75.0,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["restart_required"])

    def test_invalid_source_rejected(self) -> None:
        response = self.client.put(
            "/api/config/gps",
            json={"source": "satellite-uplink"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("source must be one of", response.json()["detail"])

    def test_uart_source_accepted_as_placeholder(self) -> None:
        response = self.client.put(
            "/api/config/gps",
            json={"source": "uart"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["gps"]["source"], "uart")
        self.assertTrue(body["restart_required"])

    def test_gpsd_partial_update_only_persists_changed_fields(self) -> None:
        # Pre-existing gpsd source with default localhost. Bumping
        # only the update interval.
        self.config.location.source = "gpsd"
        self.config.location.gpsd_host = "127.0.0.1"
        self.config.location.update_interval_seconds = 5

        response = self.client.put(
            "/api/config/gps",
            json={"source": "gpsd", "update_interval_seconds": 1},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["saved"])
        self.assertFalse(body["restart_required"])  # source did not change
        self.assertEqual(self.config.location.update_interval_seconds, 1)
        # Host untouched
        self.assertEqual(self.config.location.gpsd_host, "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
