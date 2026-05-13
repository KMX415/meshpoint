"""End-to-end tests for the /api/auth/* router.

Spins up a real FastAPI app, wires a real ``AuthService`` (with an
in-memory persistence stub), and walks the full surface: setup,
login (success/wrong/locked/setup-required), logout, cookie
attributes (HttpOnly + SameSite + Secure-when-HTTPS).
"""

from __future__ import annotations

import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.auth import dependencies as auth_deps
from src.api.auth.auth_service import AuthService
from src.api.auth.dependencies import SESSION_COOKIE_NAME
from src.api.auth.jwt_session import JwtSessionService
from src.api.auth.lockout_tracker import LockoutTracker
from src.api.auth.password_hasher import PasswordHasher
from src.api.routes import auth_routes
from src.config import WebAuthConfig

_SECRET = "auth-routes-test-secret-" + "y" * 16
_PASSWORD = "correct horse staple"


def _build_client(
    *,
    web_auth: WebAuthConfig | None = None,
    base_url: str = "http://testserver",
) -> tuple[TestClient, WebAuthConfig, list[dict]]:
    cfg = web_auth or WebAuthConfig()
    persisted: list[dict] = []
    service = AuthService(
        web_auth=cfg,
        hasher=PasswordHasher(rounds=4),
        lockout=LockoutTracker(max_attempts=3, cooldown_minutes=5),
        jwt_service=JwtSessionService(
            secret=_SECRET, expiry_minutes=60, session_version=1
        ),
        persist=lambda values: persisted.append(values),
    )
    auth_routes.init_routes(service)
    auth_deps.init_auth(service._jwt)
    app = FastAPI()
    app.include_router(auth_routes.router)
    return TestClient(app, base_url=base_url), cfg, persisted


class TestSetupEndpoint(unittest.TestCase):
    def tearDown(self) -> None:
        auth_routes.reset_routes()
        auth_deps.reset_auth()

    def test_first_setup_returns_admin_role_and_sets_cookie(self) -> None:
        client, cfg, persisted = _build_client()
        response = client.post("/api/auth/setup", json={"password": _PASSWORD})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"role": "admin"})
        self.assertIn(SESSION_COOKIE_NAME, response.cookies)
        self.assertTrue(cfg.admin_password_hash.startswith("$2"))
        self.assertEqual(len(persisted), 1)
        set_cookie_header = response.headers.get("set-cookie", "")
        lowered = set_cookie_header.lower()
        self.assertIn("httponly", lowered)
        self.assertIn("samesite=lax", lowered)
        self.assertNotIn("secure", lowered)
        self.assertIn("path=/", lowered)

    def test_second_setup_returns_409(self) -> None:
        client, _, _ = _build_client()
        client.post("/api/auth/setup", json={"password": _PASSWORD})
        response = client.post("/api/auth/setup", json={"password": "anotherpass"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "already_set")

    def test_setup_short_password_returns_400(self) -> None:
        client, _, _ = _build_client()
        response = client.post("/api/auth/setup", json={"password": "short"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "password_too_short")

    def test_setup_cookie_marked_secure_on_https(self) -> None:
        client, _, _ = _build_client(base_url="https://testserver")
        response = client.post("/api/auth/setup", json={"password": _PASSWORD})
        set_cookie_header = response.headers.get("set-cookie", "").lower()
        self.assertIn("secure", set_cookie_header)


class TestLoginEndpoint(unittest.TestCase):
    def setUp(self) -> None:
        self.client, self.cfg, _ = _build_client()
        self.client.post("/api/auth/setup", json={"password": _PASSWORD})
        self.client.cookies.clear()

    def tearDown(self) -> None:
        auth_routes.reset_routes()
        auth_deps.reset_auth()

    def test_login_success_sets_cookie(self) -> None:
        response = self.client.post(
            "/api/auth/login",
            json={"username": "admin", "password": _PASSWORD},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["role"], "admin")
        self.assertIn(SESSION_COOKIE_NAME, response.cookies)

    def test_login_wrong_password_returns_401(self) -> None:
        response = self.client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "invalid_credentials")
        self.assertNotIn(SESSION_COOKIE_NAME, response.cookies)

    def test_login_unknown_user_returns_401(self) -> None:
        response = self.client.post(
            "/api/auth/login",
            json={"username": "root", "password": _PASSWORD},
        )
        self.assertEqual(response.status_code, 401)

    def test_login_locks_after_three_failures(self) -> None:
        for _ in range(3):
            self.client.post(
                "/api/auth/login",
                json={"username": "admin", "password": "wrong"},
            )
        locked = self.client.post(
            "/api/auth/login",
            json={"username": "admin", "password": _PASSWORD},
        )
        self.assertEqual(locked.status_code, 429)
        self.assertEqual(locked.json()["detail"], "locked_out")
        self.assertIn("retry-after", {h.lower() for h in locked.headers.keys()})

    def test_login_before_setup_returns_409(self) -> None:
        auth_routes.reset_routes()
        client, _, _ = _build_client()
        response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": _PASSWORD},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "setup_required")

    def test_login_validation_rejects_blank(self) -> None:
        response = self.client.post(
            "/api/auth/login", json={"username": "", "password": ""}
        )
        self.assertEqual(response.status_code, 422)


class TestLogoutEndpoint(unittest.TestCase):
    def tearDown(self) -> None:
        auth_routes.reset_routes()
        auth_deps.reset_auth()

    def test_logout_clears_cookie(self) -> None:
        client, _, _ = _build_client()
        client.post("/api/auth/setup", json={"password": _PASSWORD})
        response = client.post("/api/auth/logout")
        self.assertEqual(response.status_code, 204)
        set_cookie_header = response.headers.get("set-cookie", "")
        self.assertIn(SESSION_COOKIE_NAME, set_cookie_header)
        self.assertIn("Max-Age=0", set_cookie_header)


class TestServiceUninitialized(unittest.TestCase):
    def tearDown(self) -> None:
        auth_routes.reset_routes()
        auth_deps.reset_auth()

    def test_calling_setup_without_init_returns_503(self) -> None:
        auth_routes.reset_routes()
        app = FastAPI()
        app.include_router(auth_routes.router)
        client = TestClient(app)
        response = client.post("/api/auth/setup", json={"password": _PASSWORD})
        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
