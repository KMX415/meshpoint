"""Relay blocklist, priority list, and dedup TTL controls."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.config import RelayConfig
from src.models.packet import Packet, PacketType, Protocol
from src.models.signal import SignalMetrics
from src.relay.dedup_filter import DeduplicationFilter
from src.relay.node_id import validate_node_ids
from src.relay.rate_limiter import RateLimiter
from src.relay.relay_manager import RelayManager


def _relay_packet(
    source_id: str = "a3f2b1c0",
    packet_id: str = "pkt001",
) -> Packet:
    return Packet(
        packet_id=packet_id,
        source_id=source_id,
        destination_id="ffffffff",
        protocol=Protocol.MESHTASTIC,
        packet_type=PacketType.TEXT,
        hop_limit=2,
        hop_start=3,
        signal=SignalMetrics(
            rssi=-95.0,
            snr=5.0,
            frequency_mhz=906.875,
            spreading_factor=11,
            bandwidth_khz=250.0,
        ),
    )


class TestRelayManagerFilters(unittest.TestCase):
    def test_blocklist_rejects_before_dedup(self):
        manager = RelayManager(
            enabled=True,
            blocklist=["a3f2b1c0"],
        )
        pkt = _relay_packet(source_id="a3f2b1c0")
        decision = manager.evaluate(pkt)
        self.assertFalse(decision.should_relay)
        self.assertEqual(decision.reason, "blocklisted")

    def test_priority_bypasses_burst_gate(self):
        manager = RelayManager(
            enabled=True,
            max_relay_per_minute=10,
            burst_size=1,
            priority_list=["deadbeef"],
        )
        first = manager.evaluate(_relay_packet(source_id="11111111", packet_id="p1"))
        second = manager.evaluate(_relay_packet(source_id="22222222", packet_id="p2"))
        self.assertTrue(first.should_relay)
        self.assertFalse(second.should_relay)
        self.assertEqual(second.reason, "rate_limited")

        priority = manager.evaluate(
            _relay_packet(source_id="deadbeef", packet_id="p3"),
        )
        self.assertTrue(priority.should_relay)
        self.assertEqual(priority.reason, "approved_priority")

    def test_reload_filters_updates_runtime_state(self):
        manager = RelayManager(enabled=True, dedup_ttl_seconds=300)
        manager.reload_filters(
            blocklist=["abcdef01"],
            priority_list=["12345678"],
            dedup_ttl_seconds=60,
        )
        self.assertEqual(manager._dedup.ttl_seconds, 60)
        pkt = _relay_packet(source_id="abcdef01")
        self.assertEqual(manager.evaluate(pkt).reason, "blocklisted")

    def test_dedup_ttl_is_configurable(self):
        dedup = DeduplicationFilter(ttl_seconds=10.0)
        dedup.set_ttl(600)
        self.assertEqual(dedup.ttl_seconds, 600)


class TestRateLimiterPriority(unittest.TestCase):
    def test_allow_priority_skips_burst_only(self):
        limiter = RateLimiter(max_per_minute=5, burst_size=1)
        self.assertTrue(limiter.allow())
        self.assertFalse(limiter.allow())
        self.assertTrue(limiter.allow_priority())


class TestValidateNodeIds(unittest.TestCase):
    def test_accepts_normalized_ids(self):
        ids = validate_node_ids(["!A3F2B1C0", "deadbeef"])
        self.assertEqual(ids, ["a3f2b1c0", "deadbeef"])

    def test_rejects_invalid_id(self):
        with self.assertRaises(ValueError):
            validate_node_ids(["not-a-node"])


class TestRelayConfigApi(unittest.TestCase):
    def setUp(self):
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
            from src.api.auth.dependencies import require_admin
            from src.api.auth.jwt_session import ROLE_ADMIN, SessionClaims
            from src.api.routes import system_config_routes as relay_cfg_module
        except ImportError as exc:
            raise unittest.SkipTest(f"API test deps unavailable: {exc}") from exc

        def _admin_claims() -> SessionClaims:
            return SessionClaims(subject="admin", role=ROLE_ADMIN, session_version=1)

        cfg = MagicMock()
        cfg.relay = RelayConfig(
            enabled=True,
            blocklist=[],
            priority_list=[],
            dedup_ttl_seconds=300,
        )
        self.manager = RelayManager(enabled=True)
        relay_cfg_module._config = cfg
        relay_cfg_module._relay_manager = self.manager
        self.app = FastAPI()
        self.app.dependency_overrides[require_admin] = _admin_claims
        from src.api.audit.dependencies import get_audit_writer

        audit = MagicMock()

        class _Ctx:
            def __enter__(self):
                return self

            def __exit__(self, *args, **kwargs):
                return False

        audit.timed_action.return_value = _Ctx()
        self.app.dependency_overrides[get_audit_writer] = lambda: audit
        self.app.include_router(relay_cfg_module.router)
        self.client = TestClient(self.app)
        self._relay_cfg_module = relay_cfg_module

    def tearDown(self):
        if hasattr(self, "_relay_cfg_module"):
            self._relay_cfg_module.reset_routes()

    def test_rejects_invalid_blocklist_id(self):
        resp = self.client.put(
            "/api/config/relay",
            json={"blocklist": ["bad-id"]},
        )
        self.assertEqual(resp.status_code, 400)

    @patch("src.api.routes.system_config_routes.save_section_to_yaml")
    def test_filter_update_hot_reloads_without_restart(self, mock_save):
        resp = self.client.put(
            "/api/config/relay",
            json={
                "blocklist": ["a3f2b1c0"],
                "priority_list": ["deadbeef"],
                "dedup_ttl_seconds": 120,
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["saved"])
        self.assertFalse(body["restart_required"])
        mock_save.assert_called_once()
        pkt = _relay_packet(source_id="a3f2b1c0")
        self.assertEqual(self.manager.evaluate(pkt).reason, "blocklisted")
        self.assertEqual(self.manager._dedup.ttl_seconds, 120)


if __name__ == "__main__":
    unittest.main()
