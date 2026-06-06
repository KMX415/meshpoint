"""LAN automation API auth and route gating."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from src.config import ApiAutomationConfig, AppConfig, load_config

_API_TOKEN = "automation-api-token-" + "y" * 16
_JWT_SECRET = "automation-test-jwt-" + "x" * 16


def _enabled_automation() -> ApiAutomationConfig:
    return ApiAutomationConfig(enabled=True, token=_API_TOKEN)


class TestAutomationConfig(unittest.TestCase):
    def test_yaml_automation_section(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "local.yaml"
            local.write_text(
                "automation:\n  enabled: true\n  token: " + _API_TOKEN + "\n",
                encoding="utf-8",
            )
            prev = os.environ.get("CONCENTRATOR_CONFIG")
            os.environ["CONCENTRATOR_CONFIG"] = str(local)
            try:
                cfg = load_config()
                self.assertTrue(cfg.automation.enabled)
                self.assertEqual(cfg.automation.token, _API_TOKEN)
            finally:
                if prev is None:
                    os.environ.pop("CONCENTRATOR_CONFIG", None)
                else:
                    os.environ["CONCENTRATOR_CONFIG"] = prev


class TestAutomationConfigEnrichment(unittest.TestCase):
    def test_token_not_exposed_in_config_payload(self) -> None:
        from src.api.routes.config_enrichment import enrich_config_payload

        cfg = AppConfig()
        cfg.automation.enabled = True
        cfg.automation.token = _API_TOKEN
        payload = enrich_config_payload(cfg, {})
        self.assertTrue(payload["automation"]["enabled"])
        self.assertTrue(payload["automation"]["token_set"])
        self.assertNotIn("token", payload["automation"])


class TestAutomationAuth(unittest.TestCase):
    def setUp(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient

            from src.api.auth import dependencies as auth_deps
            from src.api.auth.dependencies import require_automation_auth
            from src.api.auth.jwt_session import ROLE_ADMIN, JwtSessionService
        except ImportError as exc:
            raise unittest.SkipTest(f"API test deps unavailable: {exc}") from exc

        self.auth_deps = auth_deps
        self.jwt = JwtSessionService(
            secret=_JWT_SECRET, expiry_minutes=60, session_version=1
        )
        auth_deps.init_auth(self.jwt)
        auth_deps.init_automation(_enabled_automation())

        app = FastAPI()

        @app.get("/automation-gated", dependencies=[require_automation_auth])
        async def gated_route():
            return {"ok": True}

        self.client = TestClient(app)

    def tearDown(self) -> None:
        if hasattr(self, "auth_deps"):
            self.auth_deps.reset_auth()

    def test_rejects_without_credentials(self) -> None:
        response = self.client.get("/automation-gated")
        self.assertEqual(response.status_code, 401)

    def test_accepts_x_meshpoint_token(self) -> None:
        response = self.client.get(
            "/automation-gated",
            headers={"X-Meshpoint-Token": _API_TOKEN},
        )
        self.assertEqual(response.status_code, 200)

    def test_accepts_bearer_api_token(self) -> None:
        response = self.client.get(
            "/automation-gated",
            headers={"Authorization": f"Bearer {_API_TOKEN}"},
        )
        self.assertEqual(response.status_code, 200)

    def test_accepts_dashboard_jwt_bearer(self) -> None:
        from src.api.auth.jwt_session import ROLE_ADMIN

        token = self.jwt.issue("admin", ROLE_ADMIN)
        response = self.client.get(
            "/automation-gated",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 200)

    def test_rejects_wrong_token(self) -> None:
        response = self.client.get(
            "/automation-gated",
            headers={"X-Meshpoint-Token": "wrong-token"},
        )
        self.assertEqual(response.status_code, 401)

    def test_disabled_returns_403(self) -> None:
        self.auth_deps.init_automation(
            ApiAutomationConfig(enabled=False, token=_API_TOKEN)
        )
        response = self.client.get(
            "/automation-gated",
            headers={"X-Meshpoint-Token": _API_TOKEN},
        )
        self.assertEqual(response.status_code, 403)

    def test_enabled_without_token_returns_503(self) -> None:
        self.auth_deps.init_automation(
            ApiAutomationConfig(enabled=True, token="short")
        )
        response = self.client.get(
            "/automation-gated",
            headers={"X-Meshpoint-Token": _API_TOKEN},
        )
        self.assertEqual(response.status_code, 503)


class TestAutomationRoutes(unittest.TestCase):
    def setUp(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient

            from src.api.auth import dependencies as auth_deps
            from src.api.auth.jwt_session import JwtSessionService
            from src.api.routes import automation_routes
        except ImportError as exc:
            raise unittest.SkipTest(f"API test deps unavailable: {exc}") from exc

        self.auth_deps = auth_deps
        auth_deps.init_auth(
            JwtSessionService(
                secret=_JWT_SECRET, expiry_minutes=60, session_version=1
            )
        )
        auth_deps.init_automation(_enabled_automation())

        self.app = FastAPI()
        self.app.include_router(automation_routes.router)
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        if hasattr(self, "auth_deps"):
            self.auth_deps.reset_auth()

    def test_packets_requires_auth(self) -> None:
        response = self.client.get("/api/automation/packets")
        self.assertEqual(response.status_code, 401)

    def test_packets_disabled_when_automation_off(self) -> None:
        self.auth_deps.init_automation(
            ApiAutomationConfig(enabled=False, token=_API_TOKEN)
        )
        response = self.client.get(
            "/api/automation/packets",
            headers={"X-Meshpoint-Token": _API_TOKEN},
        )
        self.assertEqual(response.status_code, 403)


class TestAutomationPacketsIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        try:
            from fastapi import FastAPI
            from fastapi.testclient import TestClient

            from src.api.auth import dependencies as auth_deps
            from src.api.auth.jwt_session import JwtSessionService
            from src.api.routes import automation_routes, packets as packets_routes
        except ImportError as exc:
            raise unittest.SkipTest(f"API test deps unavailable: {exc}") from exc

        from src.storage.database import DatabaseManager
        from src.storage.packet_repository import PacketRepository

        self.auth_deps = auth_deps
        auth_deps.init_auth(
            JwtSessionService(
                secret=_JWT_SECRET, expiry_minutes=60, session_version=1
            )
        )
        auth_deps.init_automation(_enabled_automation())

        self.db = DatabaseManager(":memory:")
        await self.db.connect()
        packets_routes.init_routes(PacketRepository(self.db))

        self.app = FastAPI()
        self.app.include_router(automation_routes.router)
        self.client = TestClient(self.app)

    async def asyncTearDown(self) -> None:
        await self.db.disconnect()
        if hasattr(self, "auth_deps"):
            self.auth_deps.reset_auth()

    def test_packets_with_token_returns_list(self) -> None:
        response = self.client.get(
            "/api/automation/packets?limit=10",
            headers={"X-Meshpoint-Token": _API_TOKEN},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)
