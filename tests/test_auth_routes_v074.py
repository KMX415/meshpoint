"""HTTP-level coverage for v0.7.4 auth endpoints.

Spins up a minimal FastAPI app with just the auth router + the
``/api/config/auth_lockout`` route attached, mirrors the production
wiring (audit dependency, JWT service binding), and exercises:

- ``POST /api/auth/change_password``      -- valid + invalid current pw
- ``POST /api/auth/logout_all``           -- admin only, invalidates cookies
- ``POST /api/auth/setup_viewer``         -- admin only, weak-pw rejection
- ``POST /api/auth/clear_viewer``         -- admin only, idempotent
- ``PUT  /api/config/auth_lockout``       -- admin only, range-validated

The audit log is bound to a tmp-dir writer so each test can assert
the structured action records were written without persisting state
across cases.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.audit import AuditLogWriter
from src.api.audit import dependencies as audit_deps
from src.api.auth import dependencies as auth_deps
from src.api.auth.auth_service import AuthService
from src.api.auth.jwt_session import JwtSessionService
from src.api.auth.lockout_tracker import LockoutTracker
from src.api.auth.password_hasher import PasswordHasher
from src.api.routes import auth_config_routes, auth_routes
from src.config import WebAuthConfig

_SECRET = "v074-routes-secret-" + "z" * 32


def _build_app(tmpdir: Path) -> tuple[FastAPI, AuthService, JwtSessionService]:
    cfg = WebAuthConfig(jwt_secret=_SECRET)
    hasher = PasswordHasher(rounds=4)
    cfg.admin_password_hash = hasher.hash("originalpw")
    jwt = JwtSessionService(_SECRET, expiry_minutes=60, session_version=1)
    persisted: list[dict] = []
    svc = AuthService(
        web_auth=cfg,
        hasher=hasher,
        lockout=LockoutTracker(max_attempts=5, cooldown_minutes=5),
        jwt_service=jwt,
        persist=persisted.append,
    )
    auth_routes.init_routes(svc)
    auth_config_routes.init_routes(svc)
    auth_deps.init_auth(jwt)
    audit_deps.init_audit(AuditLogWriter(log_path=tmpdir / "audit.jsonl"))
    app = FastAPI()
    app.include_router(auth_routes.router)
    app.include_router(auth_config_routes.router)
    return app, svc, jwt


class _RoutesV074TestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.app, self.svc, self.jwt = _build_app(self.tmp_path)
        self.client = TestClient(self.app)
        self.admin_token = self.jwt.issue("admin", "admin")
        self.client.cookies.set("meshpoint_session", self.admin_token)

    def tearDown(self) -> None:
        auth_routes.reset_routes()
        auth_config_routes.reset_routes()
        auth_deps.reset_auth()
        audit_deps.reset_audit()
        self.tmp.cleanup()

    def _audit_records(self) -> list[dict]:
        path = self.tmp_path / "audit.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line]


class TestChangePasswordRoute(_RoutesV074TestBase):
    def test_success_returns_role_and_reseats_cookie(self) -> None:
        resp = self.client.post(
            "/api/auth/change_password",
            json={
                "current_password": "originalpw",
                "new_password": "newpassword1",
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"role": "admin"})
        self.assertIn("meshpoint_session", resp.cookies)
        records = self._audit_records()
        self.assertTrue(
            any(r["action"] == "auth.change_password" for r in records)
        )

    def test_invalid_current_password_returns_401(self) -> None:
        resp = self.client.post(
            "/api/auth/change_password",
            json={
                "current_password": "wrongpw",
                "new_password": "newpassword1",
            },
        )
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json()["detail"], "invalid_current_password")

    def test_short_new_password_returns_400(self) -> None:
        resp = self.client.post(
            "/api/auth/change_password",
            json={
                "current_password": "originalpw",
                "new_password": "short",
            },
        )
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["detail"], "password_too_short")

    def test_anonymous_request_rejected(self) -> None:
        client = TestClient(self.app)
        resp = client.post(
            "/api/auth/change_password",
            json={
                "current_password": "originalpw",
                "new_password": "newpassword1",
            },
        )
        self.assertEqual(resp.status_code, 401)


class TestLogoutAllRoute(_RoutesV074TestBase):
    def test_admin_bumps_session_version_and_clears_cookie(self) -> None:
        resp = self.client.post("/api/auth/logout_all")
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(self.svc.config.session_version, 2)
        self.assertIsNone(self.jwt.verify(self.admin_token))

    def test_viewer_token_is_forbidden(self) -> None:
        viewer_token = self.jwt.issue("viewer", "viewer")
        client = TestClient(self.app)
        client.cookies.set("meshpoint_session", viewer_token)
        resp = client.post("/api/auth/logout_all")
        self.assertEqual(resp.status_code, 403)


class TestSetupViewerRoute(_RoutesV074TestBase):
    def test_admin_can_provision_viewer(self) -> None:
        resp = self.client.post(
            "/api/auth/setup_viewer", json={"password": "viewerpass1"}
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(self.svc.viewer_enabled())

    def test_short_password_returns_400(self) -> None:
        resp = self.client.post(
            "/api/auth/setup_viewer", json={"password": "short"}
        )
        self.assertEqual(resp.status_code, 400)


class TestClearViewerRoute(_RoutesV074TestBase):
    def test_admin_clears_existing_viewer(self) -> None:
        self.svc.setup_viewer("viewerpass1")
        resp = self.client.post("/api/auth/clear_viewer")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(self.svc.viewer_enabled())


class TestAuthLockoutConfigRoute(_RoutesV074TestBase):
    def test_admin_updates_lockout_settings(self) -> None:
        resp = self.client.put(
            "/api/config/auth_lockout",
            json={"lockout_attempts": 7, "lockout_cooldown_minutes": 15},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["lockout_attempts"], 7)
        self.assertEqual(body["lockout_cooldown_minutes"], 15)
        self.assertEqual(self.svc.config.lockout_attempts, 7)
        self.assertEqual(self.svc.config.lockout_cooldown_minutes, 15)

    def test_out_of_range_values_rejected(self) -> None:
        resp = self.client.put(
            "/api/config/auth_lockout",
            json={"lockout_attempts": 0, "lockout_cooldown_minutes": 5},
        )
        self.assertEqual(resp.status_code, 422)


class TestAuthSessionLifetimeRoute(_RoutesV074TestBase):
    def test_admin_updates_session_lifetime(self) -> None:
        resp = self.client.put(
            "/api/config/auth_session_lifetime",
            json={"session_lifetime_minutes": 1440},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["session_lifetime_minutes"], 1440)
        self.assertEqual(self.svc.config.jwt_expiry_minutes, 1440)

    def test_below_minimum_rejected(self) -> None:
        resp = self.client.put(
            "/api/config/auth_session_lifetime",
            json={"session_lifetime_minutes": 1},
        )
        self.assertEqual(resp.status_code, 422)

    def test_above_maximum_rejected(self) -> None:
        resp = self.client.put(
            "/api/config/auth_session_lifetime",
            json={"session_lifetime_minutes": 10**9},
        )
        self.assertEqual(resp.status_code, 422)

    def test_anonymous_rejected(self) -> None:
        self.client.cookies.clear()
        resp = self.client.put(
            "/api/config/auth_session_lifetime",
            json={"session_lifetime_minutes": 1440},
        )
        self.assertEqual(resp.status_code, 401)


class TestAuthSettingsGetRoute(_RoutesV074TestBase):
    def test_admin_reads_current_settings(self) -> None:
        self.svc.update_lockout_config(max_attempts=9, cooldown_minutes=11)
        self.svc.update_session_lifetime(720)
        resp = self.client.get("/api/config/auth_settings")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["lockout_attempts"], 9)
        self.assertEqual(body["lockout_cooldown_minutes"], 11)
        self.assertEqual(body["session_lifetime_minutes"], 720)
        self.assertEqual(body["session_lifetime_min_minutes"], 5)
        self.assertEqual(body["session_lifetime_max_minutes"], 30 * 24 * 60)

    def test_anonymous_rejected(self) -> None:
        self.client.cookies.clear()
        resp = self.client.get("/api/config/auth_settings")
        self.assertEqual(resp.status_code, 401)


if __name__ == "__main__":
    unittest.main()
