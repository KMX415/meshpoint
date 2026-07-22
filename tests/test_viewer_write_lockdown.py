"""Viewer role cannot mutate config / TX / message write endpoints.

Credit: javastraat/meshpoint ``0c1cd41``.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.routes import config_routes as config_module
from src.api.routes import messages as messages_module
from src.config import AppConfig
from tests.auth_test_helpers import override_as_admin, override_as_viewer


class ViewerWriteLockdownTest(unittest.TestCase):
    def setUp(self):
        config_module._config = AppConfig()
        config_module._crypto = None
        config_module._tx_service = None
        config_module._serial_sources = []
        messages_module._tx_service = MagicMock()
        messages_module._message_repo = MagicMock()
        messages_module._meshcore_tx = None

        self.admin_app = FastAPI()
        self.admin_app.include_router(config_module.router)
        self.admin_app.include_router(messages_module.router)
        override_as_admin(self.admin_app)

        self.viewer_app = FastAPI()
        self.viewer_app.include_router(config_module.router)
        self.viewer_app.include_router(messages_module.router)
        override_as_viewer(self.viewer_app)

        self.admin = TestClient(self.admin_app)
        self.viewer = TestClient(self.viewer_app)

    def tearDown(self):
        config_module._config = None
        messages_module._tx_service = None
        messages_module._message_repo = None

    def test_viewer_cannot_put_transmit(self):
        resp = self.viewer.put("/api/config/transmit", json={"enabled": True})
        self.assertEqual(resp.status_code, 403)

    def test_viewer_cannot_send_message(self):
        resp = self.viewer.post(
            "/api/messages/send",
            json={"text": "hi", "destination": "broadcast"},
        )
        self.assertEqual(resp.status_code, 403)

    def test_viewer_config_redacts_channel_secrets(self):
        cfg = config_module._config
        cfg.meshtastic.default_key_b64 = "AQ=="
        cfg.meshtastic.channel_keys = {"Private": "wLvS00jm+SlCkdkZ6DRZXvLoqoSgPT+3vh8zX+MJoyQ="}
        cfg.meshcore.channel_keys = {"Public": "00" * 16}

        admin_body = self.admin.get("/api/config").json()
        viewer_body = self.viewer.get("/api/config").json()

        self.assertTrue(any(ch.get("psk_b64") for ch in admin_body["channels"]))
        self.assertTrue(all(ch.get("psk_b64") == "" for ch in viewer_body["channels"]))
        self.assertTrue(
            all(ck.get("key_hex") == "" for ck in viewer_body["meshcore"]["channel_keys"])
        )


if __name__ == "__main__":
    unittest.main()
