"""Integration tests for ``src.api.auth.dependencies``.

Mounts a tiny FastAPI app whose only routes use the auth dependencies
so we exercise cookie + Authorization-header extraction, role gating,
and the optional dependency under a real request lifecycle.
"""

from __future__ import annotations

import unittest

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from src.api.auth import dependencies as auth_deps
from src.api.auth.dependencies import (
    SESSION_COOKIE_NAME,
    optional_auth,
    require_admin,
    require_auth,
)
from src.api.auth.jwt_session import (
    ROLE_ADMIN,
    ROLE_VIEWER,
    JwtSessionService,
)

_SECRET = "dependencies-test-secret-" + "x" * 16


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/protected")
    def protected(claims=Depends(require_auth)):
        return {"sub": claims.subject, "role": claims.role}

    @app.get("/admin-only")
    def admin_only(claims=Depends(require_admin)):
        return {"sub": claims.subject}

    @app.get("/optional")
    def optional(claims=Depends(optional_auth)):
        if claims is None:
            return {"signed_in": False}
        return {"signed_in": True, "role": claims.role}

    return app


class TestAuthDependencies(unittest.TestCase):
    def setUp(self) -> None:
        self.service = JwtSessionService(
            secret=_SECRET, expiry_minutes=60, session_version=1
        )
        auth_deps.init_auth(self.service)
        self.app = _build_app()
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        auth_deps.reset_auth()

    def _admin_token(self) -> str:
        return self.service.issue("admin", ROLE_ADMIN)

    def _viewer_token(self) -> str:
        return self.service.issue("viewer", ROLE_VIEWER)

    def test_protected_rejects_anonymous(self) -> None:
        response = self.client.get("/protected")
        self.assertEqual(response.status_code, 401)

    def test_protected_accepts_cookie(self) -> None:
        self.client.cookies.set(SESSION_COOKIE_NAME, self._admin_token())
        response = self.client.get("/protected")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["role"], ROLE_ADMIN)

    def test_protected_accepts_bearer_header(self) -> None:
        response = self.client.get(
            "/protected",
            headers={"Authorization": f"Bearer {self._viewer_token()}"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["role"], ROLE_VIEWER)

    def test_protected_rejects_malformed_cookie(self) -> None:
        self.client.cookies.set(SESSION_COOKIE_NAME, "not-a-jwt")
        response = self.client.get("/protected")
        self.assertEqual(response.status_code, 401)

    def test_protected_rejects_when_jwt_service_uninitialized(self) -> None:
        auth_deps.reset_auth()
        self.client.cookies.set(SESSION_COOKIE_NAME, self._admin_token())
        response = self.client.get("/protected")
        self.assertEqual(response.status_code, 401)

    def test_admin_only_rejects_viewer(self) -> None:
        self.client.cookies.set(SESSION_COOKIE_NAME, self._viewer_token())
        response = self.client.get("/admin-only")
        self.assertEqual(response.status_code, 403)

    def test_admin_only_accepts_admin(self) -> None:
        self.client.cookies.set(SESSION_COOKIE_NAME, self._admin_token())
        response = self.client.get("/admin-only")
        self.assertEqual(response.status_code, 200)

    def test_optional_returns_none_for_anonymous(self) -> None:
        response = self.client.get("/optional")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"signed_in": False})

    def test_optional_returns_claims_when_authed(self) -> None:
        self.client.cookies.set(SESSION_COOKIE_NAME, self._admin_token())
        response = self.client.get("/optional")
        self.assertEqual(response.json(), {"signed_in": True, "role": ROLE_ADMIN})

    def test_optional_returns_none_for_bad_token(self) -> None:
        self.client.cookies.set(SESSION_COOKIE_NAME, "garbage")
        response = self.client.get("/optional")
        self.assertEqual(response.json(), {"signed_in": False})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
