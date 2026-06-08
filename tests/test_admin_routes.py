"""API route tests for remote ADMIN config read."""
from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock

from src.admin.reader import AdminConfigError, AdminConfigReader


class TestAdminRoutes(unittest.TestCase):
    def setUp(self):
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient
            from src.api.auth.dependencies import require_admin
            from src.api.auth.jwt_session import ROLE_ADMIN, SessionClaims
            from src.api.routes import admin_routes
        except ImportError as exc:
            raise unittest.SkipTest(f"API test deps unavailable: {exc}") from exc

        self.admin_routes = admin_routes

        def _admin_claims() -> SessionClaims:
            return SessionClaims(subject="admin", role=ROLE_ADMIN, session_version=1)

        self.reader = MagicMock(spec=AdminConfigReader)
        self.reader.available = True
        self.reader.get_status.return_value = {
            "node_id": "a3f2b1c0",
            "status": "idle",
            "section": None,
            "config": None,
            "error": "",
        }
        self.reader.request_config = AsyncMock(
            return_value={
                "node_id": "a3f2b1c0",
                "request_id": "abc",
                "status": "pending",
                "section": "device",
                "packet_id": "00000001",
            }
        )

        admin_routes.init_routes(reader=self.reader)
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
        self.app.include_router(admin_routes.router)
        self.client = TestClient(self.app)

    def tearDown(self):
        self.admin_routes.reset_routes()

    def test_status_endpoint(self):
        self.reader.available = True
        resp = self.client.get("/api/admin/remote-config/status")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["available"])

    def test_request_config_success(self):
        resp = self.client.post(
            "/api/admin/nodes/a3f2b1c0/config/request",
            json={"section": "device"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "pending")
        self.reader.request_config.assert_awaited_once()

    def test_request_config_maps_admin_error(self):
        self.reader.request_config = AsyncMock(
            side_effect=AdminConfigError("no key", status_code=503)
        )
        resp = self.client.post(
            "/api/admin/nodes/a3f2b1c0/config/request",
            json={"section": "device"},
        )
        self.assertEqual(resp.status_code, 503)
