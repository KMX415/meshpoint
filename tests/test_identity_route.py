"""Tests for the public ``GET /api/identity`` endpoint.

The endpoint is intentionally allowlisted so the auth pages can
render the identity strip pre-session. These tests pin two things:

1. The contract -- only ``device_name``, ``firmware_version``, and
   ``setup_required`` are returned. No node IDs, positions, or
   hardware fingerprints leak.
2. The ``setup_required`` flag flips correctly once the admin hash
   is set.
"""

from __future__ import annotations

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.auth import dependencies as auth_deps
from src.api.auth.auth_service import AuthService
from src.api.auth.jwt_session import JwtSessionService
from src.api.auth.lockout_tracker import LockoutTracker
from src.api.auth.password_hasher import PasswordHasher
from src.api.routes import identity_routes
from src.config import WebAuthConfig
from src.models.device_identity import DeviceIdentity

_SECRET = "identity-test-secret-" + "k" * 16


def _build_client(
    *, with_password: bool = False
) -> tuple[TestClient, WebAuthConfig, JwtSessionService]:
    cfg = WebAuthConfig()
    if with_password:
        cfg.admin_password_hash = PasswordHasher(rounds=4).hash("setup-password")
    jwt_service = JwtSessionService(
        secret=_SECRET, expiry_minutes=60, session_version=1
    )
    auth_service = AuthService(
        web_auth=cfg,
        hasher=PasswordHasher(rounds=4),
        lockout=LockoutTracker(max_attempts=5, cooldown_minutes=5),
        jwt_service=jwt_service,
        persist=lambda _values: None,
    )
    auth_deps.init_auth(jwt_service)
    identity = DeviceIdentity(
        device_id="ignored-private-id",
        device_name="MeshpointAlpha",
        latitude=12.34,
        longitude=56.78,
        altitude=99.0,
        hardware_description="RAK2287 + Raspberry Pi 4",
        firmware_version="0.7.3-test",
    )
    identity_routes.init_routes(identity, auth_service)
    app = FastAPI()
    app.include_router(identity_routes.router)
    return TestClient(app), cfg, jwt_service


class TestIdentityEndpoint(unittest.TestCase):
    def tearDown(self) -> None:
        identity_routes.reset_routes()
        auth_deps.reset_auth()

    def test_setup_required_when_no_admin_hash(self) -> None:
        client, _, _ = _build_client()
        response = client.get("/api/identity")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["device_name"], "MeshpointAlpha")
        self.assertEqual(body["firmware_version"], "0.7.3-test")
        self.assertTrue(body["setup_required"])

    def test_setup_not_required_after_password_set(self) -> None:
        client, _, _ = _build_client(with_password=True)
        response = client.get("/api/identity")
        body = response.json()
        self.assertFalse(body["setup_required"])

    def test_anonymous_response_omits_role_and_sections(self) -> None:
        client, _, _ = _build_client()
        body = client.get("/api/identity").json()
        self.assertIsNone(body.get("role"))
        self.assertIsNone(body.get("username"))
        self.assertIsNone(body.get("available_sections"))

    def test_admin_session_surfaces_full_section_list(self) -> None:
        client, _cfg, jwt = _build_client(with_password=True)
        client.cookies.set("meshpoint_session", jwt.issue("admin", "admin"))
        body = client.get("/api/identity").json()
        self.assertEqual(body["role"], "admin")
        self.assertEqual(body["username"], "admin")
        sections = set(body["available_sections"] or [])
        self.assertIn("settings.dangerous", sections)
        self.assertIn("terminal", sections)

    def test_viewer_session_omits_admin_only_sections(self) -> None:
        client, _cfg, jwt = _build_client(with_password=True)
        client.cookies.set("meshpoint_session", jwt.issue("viewer", "viewer"))
        body = client.get("/api/identity").json()
        self.assertEqual(body["role"], "viewer")
        sections = set(body["available_sections"] or [])
        self.assertNotIn("terminal", sections)
        self.assertNotIn("settings.dangerous", sections)
        self.assertIn("dashboard", sections)

    def test_response_does_not_leak_pii_fields(self) -> None:
        client, _, _ = _build_client()
        body = client.get("/api/identity").json()
        forbidden_keys = {
            "device_id",
            "latitude",
            "longitude",
            "altitude",
            "hardware_description",
            "auth_token",
        }
        leaked = forbidden_keys & set(body.keys())
        self.assertFalse(leaked, f"PII fields leaked: {leaked}")

    def test_503_when_uninitialized(self) -> None:
        identity_routes.reset_routes()
        app = FastAPI()
        app.include_router(identity_routes.router)
        response = TestClient(app).get("/api/identity")
        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
