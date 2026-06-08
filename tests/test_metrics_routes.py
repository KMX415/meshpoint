"""Tests for Prometheus /metrics exposition (PR 09)."""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.analytics.stats_reporter import StatsReporter
from src.api.routes import metrics_routes
from src.api.routes.metrics_routes import PrometheusWriter, _escape_label
from src.api.telemetry.noise_floor import NoiseFloorTracker
from src.config import MetricsConfig
from src.relay.relay_manager import RelayManager


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestPrometheusWriter(unittest.TestCase):
    def test_renders_counter_and_gauge(self) -> None:
        writer = PrometheusWriter()
        writer.counter(
            "meshpoint_packets_total",
            42,
            help="Packet count",
        )
        writer.gauge(
            "meshpoint_noise_floor_dbm",
            -108.5,
            labels={"source": "packets"},
            help="Noise floor",
        )
        text = writer.render()
        self.assertIn("# HELP meshpoint_packets_total Packet count", text)
        self.assertIn("# TYPE meshpoint_packets_total counter", text)
        self.assertIn("meshpoint_packets_total 42", text)
        self.assertIn('meshpoint_noise_floor_dbm{source="packets"} -108.5', text)

    def test_type_declared_once_with_multiple_label_sets(self) -> None:
        writer = PrometheusWriter()
        writer.counter("meshpoint_relay_rejected_total", 3, help="Rejected")
        writer.counter(
            "meshpoint_relay_rejected_total",
            1,
            labels={"reason": "rate_limit"},
        )
        text = writer.render()
        self.assertEqual(text.count("# TYPE meshpoint_relay_rejected_total"), 1)

    def test_escape_label_quotes(self) -> None:
        self.assertEqual(_escape_label('say "hi"'), 'say \\"hi\\"')


class TestMetricsRoute(unittest.TestCase):
    def _client(
        self,
        *,
        enabled: bool = True,
        require_auth: bool = False,
    ) -> TestClient:
        stats = StatsReporter()
        stats.record_packet(
            protocol="meshtastic",
            packet_type="text",
            rssi=-85.0,
            snr=8.0,
            hop_start=3,
            hop_limit=3,
        )

        traffic = MagicMock()
        traffic.get_traffic_summary = AsyncMock(
            return_value={
                "total_packets": 100,
                "packets_last_hour": 12,
                "packets_last_minute": 1,
            }
        )
        signal = MagicMock()
        signal.get_signal_summary = AsyncMock(
            return_value={"avg_rssi": -90.0, "avg_snr": 7.5, "sample_count": 5}
        )
        node_repo = MagicMock()
        node_repo.get_count = AsyncMock(return_value=8)
        node_repo.get_active_count = AsyncMock(return_value=5)

        relay = RelayManager(enabled=False, max_relay_per_minute=20, burst_size=5)
        capture = MagicMock()
        capture.concentrator_rx_stats.return_value = {
            "crc_bad_total": 2,
            "no_crc_total": 1,
        }

        metrics_routes.init_routes(
            metrics_config=MetricsConfig(
                enabled=enabled,
                require_auth=require_auth,
            ),
            stats_reporter=stats,
            signal_analyzer=signal,
            traffic_monitor=traffic,
            relay_manager=relay,
            node_repo=node_repo,
            noise_floor_tracker=NoiseFloorTracker(),
            capture_coordinator=capture,
            region="US",
        )
        app = FastAPI()
        app.include_router(metrics_routes.router)
        return TestClient(app)

    def test_disabled_returns_404(self) -> None:
        client = self._client(enabled=False)
        res = client.get("/metrics")
        self.assertEqual(res.status_code, 404)

    def test_enabled_returns_prometheus_text(self) -> None:
        client = self._client(enabled=True, require_auth=False)
        res = client.get("/metrics")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/plain", res.headers["content-type"])
        body = res.text
        self.assertIn("meshpoint_packets_session_total", body)
        self.assertIn('protocol="meshtastic"', body)
        self.assertIn("meshpoint_nodes_total", body)
        self.assertIn("meshpoint_rx_crc_bad_total", body)
        self.assertNotIn("1PG7OiAp", body)

    def test_render_metrics_async(self) -> None:
        client = self._client(enabled=True, require_auth=False)
        body = _run(metrics_routes._render_metrics())
        self.assertIn("meshpoint_uptime_seconds", body)


if __name__ == "__main__":
    unittest.main()
