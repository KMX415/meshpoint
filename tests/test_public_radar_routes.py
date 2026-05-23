"""Tests for the unauthenticated radar feed."""

from __future__ import annotations

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import public_radar_routes


class TestPublicRadarFeed(unittest.TestCase):
    def setUp(self) -> None:
        public_radar_routes.reset_state()
        self.app = FastAPI()
        self.app.include_router(public_radar_routes.router)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        public_radar_routes.reset_state()

    def test_endpoint_returns_blip_window_metadata(self) -> None:
        public_radar_routes.record_packet(rssi=-72.0)
        public_radar_routes.record_packet(rssi=-95.0)
        public_radar_routes.record_packet(rssi=None)
        response = self.client.get("/api/public/recent_rx")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 3)
        self.assertEqual(body["window_seconds"], 60)

    def test_response_does_not_leak_node_identifiers(self) -> None:
        public_radar_routes.record_packet(rssi=-80.0)
        response = self.client.get("/api/public/recent_rx").json()
        for blip in response["blips"]:
            forbidden = {"node_id", "source_id", "destination_id", "lat", "lng"}
            leaked = forbidden & set(blip.keys())
            self.assertFalse(leaked)

    def test_rssi_bucket_strong_medium_weak_unknown(self) -> None:
        public_radar_routes.record_packet(rssi=-60.0)
        public_radar_routes.record_packet(rssi=-85.0)
        public_radar_routes.record_packet(rssi=-110.0)
        public_radar_routes.record_packet(rssi=None)
        body = self.client.get("/api/public/recent_rx").json()
        buckets = [b["rssi_bucket"] for b in body["blips"]]
        self.assertEqual(
            sorted(buckets),
            ["medium", "strong", "unknown", "weak"],
        )

    def test_rate_limit_returns_429(self) -> None:
        first = self.client.get("/api/public/recent_rx")
        second = self.client.get("/api/public/recent_rx")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 429)

    def test_distance_bounds_match_contract(self) -> None:
        for rssi in (-50.0, -75.0, -120.0, None):
            public_radar_routes.record_packet(rssi=rssi)
        body = self.client.get("/api/public/recent_rx").json()
        for blip in body["blips"]:
            self.assertGreaterEqual(blip["distance"], 0.0)
            self.assertLessEqual(blip["distance"], 1.0)


if __name__ == "__main__":
    unittest.main()
