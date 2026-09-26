import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.auth.dependencies import require_admin, require_auth
from src.api.routes.pimesh_routes import build_router
from src.config import AppConfig
from src.radio.pimesh_runtime import configure_runtime, provisioned
from src.radio.pimesh_supervisor import Supervisor, atomic_json, read_json


class SwitchingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / "state.json"
        self.ready = Path(self.temp.name) / "ready.json"
        atomic_json(
            self.state,
            {"active": "meshtastic", "last_good": "meshtastic", "phase": "ready"},
        )
        self.events = []

    def supervisor(self, fail=None):
        def run(action, service):
            self.events.append((action, service))
            state = read_json(self.state)
            if action == "start" and service == "meshpoint":
                if state["active"] == fail or fail == "both":
                    return
                atomic_json(
                    self.ready,
                    {
                        "operation_id": state["operation_id"],
                        "protocol": state["active"],
                        "ready": True,
                    },
                )

        return Supervisor(self.state, self.ready, run=run, timeout=0.02)

    def test_stop_both_before_start_and_commit_after_handshake(self):
        result = self.supervisor().switch("meshcore")
        self.assertEqual(
            self.events[:4],
            [
                ("stop", "meshpoint"),
                ("stop", "meshtasticd"),
                ("stop", "meshpoint-openhop"),
                ("start", "meshpoint-openhop"),
            ],
        )
        self.assertEqual(result["last_good"], "meshcore")
        self.assertEqual(result["phase"], "ready")

    def test_failure_restores_previous_protocol(self):
        with patch("src.radio.pimesh_supervisor.time.sleep"):
            result = self.supervisor(fail="meshcore").switch("meshcore")
        self.assertEqual(result["active"], "meshtastic")
        self.assertEqual(result["last_good"], "meshtastic")
        self.assertIn("restored", result["error"])

    def test_double_failure_stops_radio_but_restores_dashboard(self):
        with patch("src.radio.pimesh_supervisor.time.sleep"):
            result = self.supervisor(fail="both").switch("meshcore")
        self.assertEqual(result["phase"], "failed")
        self.assertEqual(
            self.events[-3:],
            [
                ("stop", "meshtasticd"),
                ("stop", "meshpoint-openhop"),
                ("start", "meshpoint"),
            ],
        )

    def test_reboot_during_switch_recovers_last_good(self):
        atomic_json(
            self.state,
            {"active": "meshcore", "last_good": "meshtastic", "phase": "verifying"},
        )
        self.supervisor().recover_boot()
        self.assertEqual(read_json(self.state)["active"], "meshtastic")
        self.assertEqual(self.events[-1], ("start", "meshtasticd"))

    def test_invalid_target_has_no_side_effects(self):
        before = self.state.read_bytes()
        with self.assertRaises(ValueError):
            self.supervisor().switch("meshcore; reboot")
        self.assertEqual(self.state.read_bytes(), before)
        self.assertEqual(self.events, [])

    def test_same_protocol_is_idempotent(self):
        self.supervisor().switch("meshtastic")
        self.assertEqual(self.events, [])

    def test_stale_readiness_cannot_commit(self):
        atomic_json(
            self.ready,
            {"operation_id": "previous", "protocol": "meshcore", "ready": True},
        )
        with patch("src.radio.pimesh_supervisor.time.sleep"):
            result = self.supervisor(fail="meshcore").switch("meshcore")
        self.assertEqual(result["last_good"], "meshtastic")

    def test_stop_failure_never_starts_candidate(self):
        supervisor = self.supervisor()
        original = supervisor.run

        def run(action, service):
            if action == "stop" and service == "meshtasticd":
                raise RuntimeError("stop failed")
            original(action, service)

        supervisor.run = run
        with self.assertRaises(RuntimeError):
            supervisor.switch("meshcore")
        self.assertNotIn(("start", "meshpoint-openhop"), self.events)


class EligibilityTests(unittest.TestCase):
    def test_marker_and_explicit_matching_board_required(self):
        with tempfile.TemporaryDirectory() as directory:
            record = Path(directory) / "pimesh.json"
            atomic_json(record, {"schema": 1, "board": "pimesh-v2"})
            cfg = AppConfig()
            for platform, board in [
                ("gateway", ""),
                ("node", ""),
                ("node", "rak6421"),
                ("node", "pimesh-v1"),
            ]:
                cfg.device.platform, cfg.device.radio_hat = platform, board
                self.assertFalse(provisioned(cfg, record))
            cfg.device.radio_hat = "pimesh-v2"
            self.assertTrue(provisioned(cfg, record))
            record.unlink()
            self.assertFalse(provisioned(cfg, record))

    def test_runtime_preserves_keys_and_separates_protocols(self):
        with tempfile.TemporaryDirectory() as directory:
            marker, state = Path(directory) / "marker", Path(directory) / "state"
            atomic_json(marker, {"schema": 1, "board": "pimesh-v2"})
            atomic_json(state, {"active": "meshcore"})
            cfg = AppConfig()
            cfg.device.platform, cfg.device.radio_hat = "node", "pimesh-v2"
            cfg.meshcore.channel_keys = {"test": "example"}
            configure_runtime(cfg, marker, state)
            self.assertEqual(cfg.capture.sources, ["meshcore_usb"])
            self.assertEqual(cfg.capture.meshcore_usb.connection_type, "tcp")
            self.assertEqual(cfg.meshcore.channel_keys, {"test": "example"})
            atomic_json(state, {"active": "meshtastic"})
            configure_runtime(cfg, marker, state)
            self.assertEqual(cfg.capture.sources, ["meshtasticd"])

    def test_non_pimesh_api_rejects_even_admin(self):
        app = FastAPI()
        app.include_router(build_router(AppConfig()))
        app.dependency_overrides[require_admin] = lambda: None
        app.dependency_overrides[require_auth] = lambda: None
        with TestClient(app) as client:
            self.assertEqual(client.get("/api/pimesh/status").status_code, 404)
            self.assertEqual(
                client.post(
                    "/api/pimesh/protocol", json={"protocol": "meshcore"}
                ).status_code,
                404,
            )

    def test_unauthenticated_mutation_denied(self):
        app = FastAPI()
        app.include_router(build_router(AppConfig()))
        with TestClient(app) as client:
            self.assertEqual(
                client.post(
                    "/api/pimesh/protocol", json={"protocol": "meshcore"}
                ).status_code,
                401,
            )

    def test_busy_rejects_second_operation(self):
        app = FastAPI()
        app.include_router(build_router(AppConfig()))
        app.dependency_overrides[require_admin] = lambda: None
        with (
            patch("src.api.routes.pimesh_routes.provisioned", return_value=True),
            patch(
                "src.api.routes.pimesh_routes.read_json",
                return_value={"phase": "starting"},
            ),
            TestClient(app) as client,
        ):
            self.assertEqual(
                client.post(
                    "/api/pimesh/protocol", json={"protocol": "meshcore"}
                ).status_code,
                409,
            )


class TransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_tcp_does_not_probe_serial(self):
        from src.capture.meshcore_usb_source import MeshcoreUsbCaptureSource

        source = MeshcoreUsbCaptureSource(
            connection_type="tcp", tcp_host="localhost", tcp_port=5000
        )
        with patch("src.capture.meshcore_usb_detect.detect_meshcore_port") as detect:
            self.assertEqual(await source._resolve_port(), "tcp://localhost:5000")
            detect.assert_not_called()

    async def test_tcp_retains_connection_ownership_on_handshake_failure(self):
        from src.capture.meshcore_usb_source import MeshcoreUsbCaptureSource

        source = MeshcoreUsbCaptureSource(connection_type="tcp")
        instance = MagicMock()
        instance.connect = AsyncMock(return_value=None)
        instance.disconnect = AsyncMock()
        instance.stop_auto_message_fetching = AsyncMock()
        with (
            patch("meshcore.MeshCore", return_value=instance),
            patch("meshcore.tcp_cx.TCPConnection") as tcp,
        ):
            await source._connect("tcp://localhost:5000")
            tcp.assert_called_once_with("127.0.0.1", 5000)
        instance.disconnect.assert_awaited_once()
        self.assertFalse(source.connected)

    def test_ipc_timeout_rejects_late_success(self):
        import queue

        from src.capture.meshtasticd_bridge_source import MeshtasticdBridgeSource

        source = MeshtasticdBridgeSource()
        source._cmd_queue, source._resp_queue = MagicMock(), MagicMock()
        source._resp_queue.get.side_effect = queue.Empty()
        self.assertFalse(source.request_read_radio_state()[0])
        source._resp_queue.get.side_effect = None
        source._resp_queue.get.return_value = ("ok", {"packet_id": "12345678"})
        self.assertFalse(source.request_send_text("test", 0xFFFFFFFF)[0])
        self.assertEqual(source._cmd_queue.put.call_count, 1)
