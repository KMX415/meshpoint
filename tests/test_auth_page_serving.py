"""Integration tests for /setup and /login HTML serving.

These pages are mounted on ``server.py`` *before* the static catch-
all so a visitor can hit ``/setup`` or ``/login`` directly. The
tests below pin three things:

1. Both routes return 200 with a real HTML payload.
2. The radar shell, identity strip, and form are present.
3. The login page surfaces the SSH recovery hint per the auth plan.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.server import _serve_auth_page

_FRONTEND = Path(__file__).resolve().parents[1] / "frontend"


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.get("/setup")
    async def setup_page():
        return _serve_auth_page(_FRONTEND, "setup.html")

    @app.get("/login")
    async def login_page():
        return _serve_auth_page(_FRONTEND, "login.html")

    return app


class TestAuthPageServing(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(_build_app())

    def test_setup_page_returns_html_with_radar_and_form(self) -> None:
        response = self.client.get("/setup")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        body = response.text
        self.assertIn("First-time setup", body)
        self.assertIn('id="auth-form"', body)
        self.assertIn('id="password-input"', body)
        self.assertIn('id="confirm-input"', body)
        self.assertIn('class="auth-radar', body)
        self.assertIn('data-auth-mode="setup"', body)

    def test_login_page_returns_html_with_recovery_hint(self) -> None:
        response = self.client.get("/login")
        self.assertEqual(response.status_code, 200)
        body = response.text
        self.assertIn('id="username-input"', body)
        self.assertIn('id="password-input"', body)
        self.assertIn('class="auth-radar', body)
        self.assertIn("ssh pi@", body)
        self.assertIn("meshpoint reset-password", body)
        self.assertIn('data-auth-mode="login"', body)

    def test_setup_page_does_not_leak_login_recovery_hint(self) -> None:
        body = self.client.get("/setup").text
        self.assertNotIn("meshpoint reset-password", body)

    def test_404_for_unknown_auth_page(self) -> None:
        app = FastAPI()

        @app.get("/missing")
        async def missing():
            return _serve_auth_page(_FRONTEND, "does-not-exist.html")

        response = TestClient(app).get("/missing")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
