"""Tests for the POST /api/messages/advert endpoint.

Regression coverage for the Send Advert button bug: previously the
button POSTed empty text to /api/messages/send and was rejected by
the empty-text validation before reaching MeshCore.
"""

from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import messages as messages_module


class _AdvertResult:
    def __init__(self, success: bool, error: str | None = None,
                 event_type: str | None = None):
        self.success = success
        self.error = error
        self.event_type = event_type


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(messages_module.router)
    from tests.auth_test_helpers import override_as_admin
    override_as_admin(app)
    return app


def _reset_module_state() -> None:
    messages_module._tx_service = None
    messages_module._message_repo = None
    messages_module._node_repo = None
    messages_module._meshcore_tx = None
    messages_module._config = None


class TestSendMeshCoreAdvertEndpoint(unittest.TestCase):

    def setUp(self) -> None:
        _reset_module_state()
        self.app = _build_app()
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        _reset_module_state()

    def test_503_when_meshcore_tx_missing(self):
        messages_module._meshcore_tx = None
        res = self.client.post("/api/messages/advert", json={})
        self.assertEqual(res.status_code, 503)
        self.assertIn("not connected", res.json()["detail"].lower())

    def test_503_when_meshcore_tx_disconnected(self):
        mc = MagicMock()
        mc.connected = False
        messages_module._meshcore_tx = mc
        res = self.client.post("/api/messages/advert", json={})
        self.assertEqual(res.status_code, 503)

    def test_success_calls_send_advert_and_returns_payload(self):
        mc = MagicMock()
        mc.connected = True
        mc.send_advert = AsyncMock(
            return_value=_AdvertResult(success=True, event_type="ADVERT_OK")
        )
        messages_module._meshcore_tx = mc

        res = self.client.post("/api/messages/advert", json={})

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertTrue(body["success"])
        self.assertIsNone(body["error"])
        self.assertEqual(body["event_type"], "ADVERT_OK")
        mc.send_advert.assert_awaited_once_with(flood=False)

    def test_failure_returns_error_in_body(self):
        mc = MagicMock()
        mc.connected = True
        mc.send_advert = AsyncMock(
            return_value=_AdvertResult(success=False, error="Advert timed out")
        )
        messages_module._meshcore_tx = mc

        res = self.client.post("/api/messages/advert", json={})

        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertFalse(body["success"])
        self.assertEqual(body["error"], "Advert timed out")

    def test_flood_query_param_passed_through(self):
        mc = MagicMock()
        mc.connected = True
        mc.send_advert = AsyncMock(
            return_value=_AdvertResult(success=True, event_type="ADVERT_OK")
        )
        messages_module._meshcore_tx = mc

        res = self.client.post("/api/messages/advert?flood=true", json={})

        self.assertEqual(res.status_code, 200)
        mc.send_advert.assert_awaited_once_with(flood=True)


if __name__ == "__main__":
    unittest.main()
