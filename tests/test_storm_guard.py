"""Storm guard quarantine (PR 12)."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.config import RelayConfig, StormGuardConfig
from src.models.packet import Packet, PacketType, Protocol
from src.models.signal import SignalMetrics
from src.relay.relay_manager import RelayManager
from src.relay.storm_guard import StormGuard


def _packet(
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


class FakeClock:
    def __init__(self, start: float = 1000.0) -> None:
        self._now = start

    def now(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


class TestStormGuard(unittest.TestCase):
    def _guard(self, **overrides) -> tuple[StormGuard, FakeClock]:
        clock = FakeClock()
        base = {
            "enabled": True,
            "window_seconds": 60,
            "identical_packet_threshold": 3,
            "rate_threshold_per_minute": 5,
            "quarantine_duration_seconds": 120,
        }
        base.update(overrides)
        cfg = StormGuardConfig(**base)
        return StormGuard(cfg, now_fn=clock.now), clock

    def test_identical_packet_storm_quarantines(self):
        guard, clock = self._guard()
        for _ in range(3):
            guard.observe(_packet(packet_id="same-id"))
            clock.advance(1)
        self.assertTrue(guard.is_quarantined("a3f2b1c0"))
        entry = guard.get_entry("a3f2b1c0")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.reason, "identical_packet_storm")

    def test_rate_storm_quarantines(self):
        guard, clock = self._guard(identical_packet_threshold=99)
        for i in range(5):
            guard.observe(_packet(packet_id=f"p{i}"))
            clock.advance(1)
        self.assertTrue(guard.is_quarantined("a3f2b1c0"))
        self.assertEqual(guard.get_entry("a3f2b1c0").reason, "rate_storm")

    def test_auto_release_after_duration(self):
        guard, clock = self._guard()
        for _ in range(3):
            guard.observe(_packet(packet_id="dup"))
            clock.advance(1)
        self.assertTrue(guard.is_quarantined("a3f2b1c0"))
        clock.advance(121)
        self.assertFalse(guard.is_quarantined("a3f2b1c0"))
        self.assertEqual(guard.snapshot(), [])

    def test_manual_release_clears_state(self):
        guard, _clock = self._guard()
        for _ in range(3):
            guard.observe(_packet(packet_id="dup"))
        self.assertTrue(guard.release("a3f2b1c0"))
        self.assertFalse(guard.is_quarantined("a3f2b1c0"))

    def test_on_quarantine_callback_fires_once(self):
        guard, _clock = self._guard()
        seen = []
        guard.set_on_quarantine(lambda entry: seen.append(entry.node_id))
        for _ in range(3):
            guard.observe(_packet(packet_id="dup"))
        guard.observe(_packet(packet_id="dup"))
        self.assertEqual(seen, ["a3f2b1c0"])


class TestRelayManagerStormGuard(unittest.IsolatedAsyncioTestCase):
    async def test_storm_quarantined_rejects_relay(self):
        guard, _clock = TestStormGuard()._guard()
        for _ in range(3):
            guard.observe(_packet(packet_id="dup"))
        manager = RelayManager(enabled=True, storm_guard=guard)
        decision = manager.evaluate(_packet(packet_id="new"))
        self.assertFalse(decision.should_relay)
        self.assertEqual(decision.reason, "storm_quarantined")

    async def test_blocklist_checked_before_quarantine(self):
        guard, _clock = TestStormGuard()._guard()
        for _ in range(3):
            guard.observe(_packet(packet_id="dup"))
        manager = RelayManager(
            enabled=True,
            blocklist=["a3f2b1c0"],
            storm_guard=guard,
        )
        decision = manager.evaluate(_packet())
        self.assertEqual(decision.reason, "blocklisted")


class TestRelayQuarantineApi(unittest.TestCase):
    def setUp(self):
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
            from src.api.auth.dependencies import require_admin
            from src.api.auth.jwt_session import ROLE_ADMIN, SessionClaims
            from src.api.routes import relay_routes as relay_api
        except ImportError as exc:
            raise unittest.SkipTest(f"API test deps unavailable: {exc}") from exc

        def _admin_claims() -> SessionClaims:
            return SessionClaims(subject="admin", role=ROLE_ADMIN, session_version=1)

        cfg = MagicMock()
        cfg.relay = RelayConfig(
            enabled=True,
            blocklist=[],
            storm_guard=StormGuardConfig(enabled=True),
        )
        guard = StormGuard(cfg.relay.storm_guard)
        for _ in range(3):
            guard.observe(_packet(packet_id="dup"))
        self.manager = RelayManager(enabled=True, storm_guard=guard)
        relay_api._config = cfg
        relay_api._relay_manager = self.manager
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
        self.app.include_router(relay_api.router)
        self.client = TestClient(self.app)
        self._relay_api = relay_api

    def tearDown(self):
        if hasattr(self, "_relay_api"):
            self._relay_api.reset_routes()

    def test_list_quarantine(self):
        resp = self.client.get("/api/relay/quarantine")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["enabled"])
        self.assertEqual(len(body["entries"]), 1)

    @patch("src.api.routes.relay_routes.save_section_to_yaml")
    def test_promote_to_blocklist(self, mock_save):
        resp = self.client.post("/api/relay/quarantine/a3f2b1c0/blocklist")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["blocklisted"])
        self.assertIn("a3f2b1c0", body["blocklist"])
        mock_save.assert_called_once()
        self.assertFalse(self.manager.storm_guard.is_quarantined("a3f2b1c0"))
        self.assertEqual(
            self.manager.evaluate(_packet()).reason,
            "blocklisted",
        )


if __name__ == "__main__":
    unittest.main()
