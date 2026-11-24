"""Reticulum boundary checks without network, devices, or optional libraries."""
import asyncio
import base64
import hashlib
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
import zipfile
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.auth import dependencies as auth
from src.api.auth.jwt_session import JwtSessionService
from src.config import AppConfig
from src.plugins import python_dependencies as deps
from apps.reticulum.backend.worker_proxy import ReticulumWorker, build_router
from apps.reticulum.backend.rns_config import render_config


class TestDependencyRecipe(unittest.TestCase):
    def test_tampered_wheel_is_rejected_without_placing_code(self):
        with tempfile.TemporaryDirectory() as temp:
            apps = Path(temp) / "apps"
            with patch.object(deps, "_download", return_value=b"tampered"):
                with self.assertRaisesRegex(ValueError, "checksum"):
                    deps.install_reticulum(apps)
            self.assertFalse(deps.environment_dir(apps).exists())

    def test_only_optional_package_trees_are_extracted(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("RNS/__init__.py", "# optional")
            archive.writestr("cryptography/__init__.py", "# must not replace core")
            archive.writestr("scripts/setup.py", "# must not execute")
        data = buffer.getvalue()
        recipe = (("RNS", "test", "unused", hashlib.sha256(data).hexdigest()),)
        with tempfile.TemporaryDirectory() as temp:
            apps = Path(temp) / "apps"
            with patch.object(deps, "WHEELS", recipe), patch.object(deps, "_download", return_value=data):
                self.assertTrue(deps.install_reticulum(apps)["ready"])
                self.assertTrue(deps.is_ready(apps))
                self.assertTrue(deps.install_reticulum(apps)["already_installed"])
            base = deps.environment_dir(apps)
            self.assertTrue((base / "RNS" / "__init__.py").exists())
            self.assertFalse((base / "cryptography").exists())
            self.assertFalse((base / "scripts").exists())

    def test_archive_traversal_rejected(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("RNS/../../escape.py", "bad")
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                deps._extract(buffer.getvalue(), "RNS", Path(temp))


class TestReticulumProxy(unittest.TestCase):
    def setUp(self):
        self.jwt = JwtSessionService("reticulum-tests-" + "x" * 32, 60, 1)
        auth.init_auth(self.jwt)
        self.worker = SimpleNamespace(request=AsyncMock(return_value={
            "status": 200, "body": base64.b64encode(b'{"running":true}').decode(),
            "headers": [["content-type", "application/json"]],
        }))
        app = FastAPI()
        app.include_router(build_router({"service": self.worker}))
        @app.get("/api/core-health")
        def health():
            return {"ok": True}
        self.client = TestClient(app)

    def tearDown(self):
        auth.reset_auth()

    def test_all_plugin_requests_require_admin(self):
        self.assertEqual(self.client.get("/api/reticulum/conversations").status_code, 401)
        self.client.cookies.set("meshpoint_session", self.jwt.issue("viewer", "viewer"))
        self.assertEqual(self.client.get("/api/reticulum/status").status_code, 403)
        self.assertEqual(self.client.put("/api/config/reticulum", json={}).status_code, 403)
        self.worker.request.assert_not_called()

    def test_admin_request_uses_private_worker(self):
        self.client.cookies.set("meshpoint_session", self.jwt.issue("admin", "admin"))
        self.assertTrue(self.client.get("/api/reticulum/status").json()["running"])
        self.assertEqual(self.worker.request.call_args.args[4], "admin")

    def test_worker_failure_does_not_stop_core_routes(self):
        self.client.cookies.set("meshpoint_session", self.jwt.issue("admin", "admin"))
        self.worker.request.side_effect = RuntimeError("worker stopped")
        self.assertEqual(self.client.get("/api/reticulum/status").status_code, 503)
        self.assertEqual(self.client.get("/api/core-health").json(), {"ok": True})


class TestReticulumConfiguration(unittest.IsolatedAsyncioTestCase):
    async def test_dead_daemon_invalidates_and_stops_only_worker(self):
        from unittest.mock import Mock
        import psutil
        worker = ReticulumWorker(Path("unused"), {}, SimpleNamespace())
        worker.daemon_identity = (123, 456)
        worker.process = Mock(returncode=None)
        with patch("apps.reticulum.backend.worker_proxy.psutil.Process", side_effect=psutil.NoSuchProcess(123)):
            with patch("apps.reticulum.backend.worker_proxy.asyncio.sleep", new_callable=AsyncMock):
                await worker._monitor_daemon()
        self.assertIn("daemon stopped", worker.failure)
        worker.process.terminate.assert_called_once()

    async def test_feed_urls_and_redirects_reject_non_http_schemes(self):
        from apps.reticulum.backend.http import HTTPRedirect, validate_url
        from urllib.request import Request
        for url in ("file:///etc/passwd", "ftp://example.org/feed", "https://user:pass@example.org"):
            with self.subTest(url=url):
                with self.assertRaises(ValueError):
                    validate_url(url)
                with self.assertRaises(ValueError):
                    HTTPRedirect().redirect_request(Request("https://example.org"), None, 302, "", {}, url)
        validate_url("https://example.org/feed")
        validate_url("http://localhost/feed")

    async def test_default_config_has_no_active_interfaces(self):
        rendered = render_config({})
        self.assertNotIn("enabled = Yes", rendered)
        self.assertNotIn("TCPClientInterface", rendered)
        self.assertNotIn("RNodeInterface", rendered)

    async def test_config_injection_rejected(self):
        with self.assertRaises(ValueError):
            render_config({"backbone_host": "host\n[[injected]]"})

    async def test_core_port_cannot_be_reused(self):
        config = AppConfig()
        config.capture.meshcore_usb.serial_port = "COM9"
        context = SimpleNamespace(config=config, pipeline=None, ws_manager=None, plugin_lock=asyncio.Lock())
        worker = ReticulumWorker(Path("unused"), {"rnode_enabled": True, "rnode_serial_port": "COM9"}, context)
        with patch("asyncio.create_subprocess_exec", new_callable=AsyncMock) as spawn:
            with self.assertRaisesRegex(ValueError, "already assigned"):
                await worker.start()
            spawn.assert_not_called()

    async def test_auto_detected_core_port_is_reserved(self):
        config = AppConfig()
        capture = SimpleNamespace(_sources=[SimpleNamespace(_resolved_port="COM7")])
        context = SimpleNamespace(config=config, pipeline=SimpleNamespace(capture_coordinator=capture))
        worker = ReticulumWorker(Path("unused"), {}, context)
        with self.assertRaisesRegex(ValueError, "already assigned"):
            worker._check_port({"rnode_enabled": True, "rnode_serial_port": "COM7"})
