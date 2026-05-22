"""Tests for Configuration → Meshradar upstream API routes."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.auth.dependencies import require_admin
from src.api.auth.jwt_session import ROLE_ADMIN, SessionClaims
from src.api.routes import upstream_config_routes as upstream_module
from src.config import UpstreamConfig


def _admin_claims() -> SessionClaims:
    return SessionClaims(subject="admin", role=ROLE_ADMIN, session_version=1)


def _build_app() -> FastAPI:
    app = FastAPI()
    app.dependency_overrides[require_admin] = _admin_claims
    app.include_router(upstream_module.router)
    return app


class TestUpstreamUpdate(unittest.TestCase):
    def setUp(self) -> None:
        cfg = MagicMock()
        cfg.upstream = UpstreamConfig(enabled=True, auth_token="existing")
        upstream_module._config = cfg
        self.client = TestClient(_build_app())

    def tearDown(self) -> None:
        upstream_module.reset_routes()

    def test_does_not_accept_enabled_field(self) -> None:
        with patch("src.api.routes.upstream_config_routes.save_section_to_yaml") as mock_save:
            resp = self.client.put(
                "/api/config/upstream",
                json={
                    "enabled": False,
                    "url": "wss://api.meshradar.io",
                    "reconnect_interval_seconds": 15,
                    "buffer_max_size": 4000,
                    "auth_token_unchanged": True,
                },
            )
        self.assertEqual(resp.status_code, 200)
        saved = mock_save.call_args[0][1]
        self.assertNotIn("enabled", saved)
        self.assertTrue(upstream_module._config.upstream.enabled)

    def test_status_omits_enabled(self) -> None:
        status = upstream_module.build_upstream_status(upstream_module._config.upstream)
        self.assertNotIn("enabled", status)
