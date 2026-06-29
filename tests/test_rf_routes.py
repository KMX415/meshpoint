"""Tests for GET /api/rf/status."""
from __future__ import annotations

import time
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.telemetry.noise_floor import NoiseFloorTracker, SOURCE_PACKETS
from src.api.telemetry.spectral_scan_service import SpectralScanService
from src.api.routes import rf_routes
from src.config import AppConfig, RadioConfig
from src.hal.sx1302_spectral_scan import SpectralScanResult


class _FakeWrapper:
    spectral_scan_supported = True

    def run_spectral_scan(self, frequency_hz: int, nb_scan: int = 1024):
        return None


def _histogram_result() -> SpectralScanResult:
    levels = tuple([-120 + i * 2 for i in range(35)])
    counts = tuple([0] * 34 + [40])
    return SpectralScanResult(
        levels_dbm=levels,
        counts=counts,
        frequency_hz=906_875_000,
        nb_scan=1024,
        timestamp=time.time(),
    )


class TestRfRoutes(unittest.TestCase):
    def _client(
        self,
        *,
        interval: float = 60.0,
        scan_service: SpectralScanService | None = None,
    ) -> TestClient:
        tracker = NoiseFloorTracker()
        config = AppConfig(radio=RadioConfig(spectral_scan_interval_seconds=interval))
        rf_routes.init_routes(tracker, scan_service, config)
        app = FastAPI()
        app.include_router(rf_routes.router)
        return TestClient(app)

    def test_status_returns_noise_floor_snapshot(self) -> None:
        tracker = NoiseFloorTracker()
        tracker.update(rssi_dbm=-90, snr_db=8, bandwidth_khz=250)
        tracker.update(rssi_dbm=-88, snr_db=6, bandwidth_khz=250)
        config = AppConfig(radio=RadioConfig(spectral_scan_interval_seconds=0))
        rf_routes.init_routes(tracker, None, config)
        app = FastAPI()
        app.include_router(rf_routes.router)
        client = TestClient(app)

        res = client.get("/api/rf/status")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["noise_floor"]["source"], SOURCE_PACKETS)
        self.assertFalse(body["spectral_scan"]["enabled"])
        self.assertIsNone(body["spectral_scan"]["histogram"])

    def test_scan_disabled_message_when_interval_zero(self) -> None:
        client = self._client(interval=0)
        body = client.get("/api/rf/status").json()
        self.assertIn("interval_seconds is 0", body["spectral_scan"]["message"])

    def test_fleet_fallback_note_when_scan_unavailable(self) -> None:
        client = self._client(interval=60.0, scan_service=None)
        scan = client.get("/api/rf/status").json()["spectral_scan"]
        self.assertTrue(scan["fleet_expected_fallback"])
        self.assertIn("RAK V2", scan["message"])
        self.assertIn("packet fallback", scan["message"])

    def test_histogram_exposed_after_scan(self) -> None:
        wrapper = _FakeWrapper()
        wrapper.run_spectral_scan = lambda *_a, **_k: _histogram_result()  # type: ignore[method-assign]
        tracker = NoiseFloorTracker()
        service = SpectralScanService(
            wrapper=wrapper,
            tracker=tracker,
            frequency_hz=906_875_000,
            bandwidth_khz=250,
            interval_seconds=5,
            startup_delay_seconds=0,
        )
        service._publish(_histogram_result())

        client = self._client(scan_service=service)
        body = client.get("/api/rf/status").json()
        hist = body["spectral_scan"]["histogram"]
        self.assertIsNotNone(hist)
        self.assertEqual(len(hist["levels_dbm"]), 35)
        self.assertGreater(hist["total_samples"], 0)


if __name__ == "__main__":
    unittest.main()
