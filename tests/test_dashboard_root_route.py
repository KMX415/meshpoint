"""Regression tests for the v0.7.3.1 dashboard-root auth gate.

v0.7.3 mounted ``StaticFiles(directory=..., html=True)`` on ``/``,
which served ``index.html`` to anyone without checking the session
cookie. A stale browser tab against an upgraded server could then
load the new SPA JS, fight an unauthenticated ``/ws`` upgrade, and
get stranded in the reconnect loop documented in
``test_websocket_auth_close_code.py``.

The v0.7.3.1 fix adds an explicit ``@app.get("/")`` route registered
*before* the StaticFiles mount that:

- 302s to ``/setup`` if the admin password has not been set yet
- 302s to ``/login`` if it has but the request has no valid cookie
- serves ``index.html`` for valid sessions

These tests exercise the helper directly, the route in isolation,
and the full server-style precedence with a static-mount sibling so
a future refactor cannot accidentally let the static catch-all win.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.testclient import TestClient

from src.api.auth.dependencies import SESSION_COOKIE_NAME
from src.api.auth.jwt_session import ROLE_ADMIN, JwtSessionService
from src.api.server import _request_has_valid_session

_SECRET = "dashboard-root-test-secret-" + "y" * 16


def _service() -> JwtSessionService:
    return JwtSessionService(secret=_SECRET, expiry_minutes=60, session_version=1)


class _StubAuthService:
    def __init__(self, setup_complete: bool) -> None:
        self._setup_complete = setup_complete

    def is_setup_complete(self) -> bool:
        return self._setup_complete


def _build_test_app(
    static_dir: Path, jwt_service, auth_service
) -> FastAPI:
    """Mirror the wiring used by ``server.create_app`` for ``/``."""
    app = FastAPI()

    @app.get("/", include_in_schema=False)
    async def serve_dashboard_root(request: Request):
        if not _request_has_valid_session(request, jwt_service):
            target = "/login" if auth_service.is_setup_complete() else "/setup"
            return RedirectResponse(url=target, status_code=302)
        return FileResponse(
            str(static_dir / "index.html"), media_type="text/html"
        )

    @app.get("/login", include_in_schema=False)
    async def serve_login():
        return FileResponse(
            str(static_dir / "login.html"), media_type="text/html"
        )

    @app.get("/setup", include_in_schema=False)
    async def serve_setup():
        return FileResponse(
            str(static_dir / "setup.html"), media_type="text/html"
        )

    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True))

    return app


class _StaticDir:
    """Build a throwaway frontend dir with all the files the route may serve."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name)
        (self.path / "index.html").write_text(
            "<!doctype html><html><body>dashboard SPA</body></html>"
        )
        (self.path / "login.html").write_text("<html>login</html>")
        (self.path / "setup.html").write_text("<html>setup</html>")
        css_dir = self.path / "css"
        css_dir.mkdir()
        (css_dir / "dashboard.css").write_text("/* dashboard */")

    def cleanup(self) -> None:
        self._tmp.cleanup()


class TestDashboardRootRedirects(unittest.TestCase):
    def setUp(self) -> None:
        self.static = _StaticDir()
        self.service = _service()

    def tearDown(self) -> None:
        self.static.cleanup()

    def _client(self, setup_complete: bool) -> TestClient:
        return TestClient(
            _build_test_app(
                self.static.path,
                self.service,
                _StubAuthService(setup_complete=setup_complete),
            ),
            follow_redirects=False,
        )

    def test_unauthed_with_setup_complete_redirects_to_login(self) -> None:
        response = self._client(setup_complete=True).get("/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/login")

    def test_unauthed_without_setup_complete_redirects_to_setup(self) -> None:
        response = self._client(setup_complete=False).get("/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/setup")

    def test_invalid_cookie_redirects_to_login(self) -> None:
        client = self._client(setup_complete=True)
        client.cookies.set(SESSION_COOKIE_NAME, "not-a-jwt")
        response = client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["location"], "/login")

    def test_valid_cookie_serves_dashboard_html(self) -> None:
        token = self.service.issue("admin", ROLE_ADMIN)
        client = self._client(setup_complete=True)
        client.cookies.set(SESSION_COOKIE_NAME, token)
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("dashboard SPA", response.text)

    def test_static_assets_still_served_through_mount(self) -> None:
        """Static asset paths (e.g. /css/foo.css) must NOT be auth-gated.

        Only the bare ``/`` is redirected; CSS/JS/asset siblings keep
        flowing through ``StaticFiles`` so the login page itself can
        load its bundled stylesheet from an unauthenticated session.
        """
        client = self._client(setup_complete=True)
        response = client.get("/css/dashboard.css")
        self.assertEqual(response.status_code, 200)
        self.assertIn("dashboard", response.text)


class TestRequestHasValidSessionHelper(unittest.TestCase):
    """Pin behaviour of the cookie-only helper used by the root gate."""

    def test_returns_false_when_jwt_service_is_none(self) -> None:
        request = _stub_request(cookies={SESSION_COOKIE_NAME: "anything"})
        self.assertFalse(_request_has_valid_session(request, None))

    def test_returns_false_when_no_cookie(self) -> None:
        self.assertFalse(
            _request_has_valid_session(_stub_request(cookies={}), _service())
        )

    def test_returns_false_when_cookie_invalid(self) -> None:
        self.assertFalse(
            _request_has_valid_session(
                _stub_request(cookies={SESSION_COOKIE_NAME: "garbage"}),
                _service(),
            )
        )

    def test_returns_true_when_cookie_valid(self) -> None:
        service = _service()
        token = service.issue("admin", ROLE_ADMIN)
        self.assertTrue(
            _request_has_valid_session(
                _stub_request(cookies={SESSION_COOKIE_NAME: token}),
                service,
            )
        )


def _stub_request(*, cookies: dict) -> Request:
    """Build a Request with the cookie jar populated.

    Faster than spinning up a TestClient for each helper-level case.
    """
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [
            (
                b"cookie",
                "; ".join(f"{k}={v}" for k, v in cookies.items()).encode(),
            )
        ]
        if cookies
        else [],
        "query_string": b"",
    }
    return Request(scope)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
