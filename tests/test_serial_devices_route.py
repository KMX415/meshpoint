"""PUT /api/config/capture/serial-devices route tests.

Credit: javastraat/meshpoint ``9af5625``.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.auth.jwt_session import SessionClaims
from src.api.routes import system_config_routes
from src.config import AppConfig


class SerialDevicesRouteTest(unittest.TestCase):
    def setUp(self):
        self.config = AppConfig()
        self.config.capture.sources = ["concentrator"]
        system_config_routes.init_routes(self.config)

        app = FastAPI()
        app.include_router(system_config_routes.router)

        async def _admin():
            return SessionClaims(
                subject="admin", role="admin", session_version=1
            )

        from src.api.auth.dependencies import require_admin
        from src.api.audit.dependencies import get_audit_writer

        app.dependency_overrides[require_admin] = _admin
        app.dependency_overrides[get_audit_writer] = lambda: MagicMock(
            timed_action=MagicMock(
                return_value=MagicMock(
                    __enter__=MagicMock(return_value=None),
                    __exit__=MagicMock(return_value=False),
                )
            )
        )
        self.client = TestClient(app)

    def tearDown(self):
        system_config_routes.reset_routes()

    @patch("src.api.routes.system_config_routes.save_section_to_yaml")
    def test_put_replaces_device_list(self, save_mock):
        resp = self.client.put(
            "/api/config/capture/serial-devices",
            json={
                "enable_source": True,
                "devices": [
                    {"label": "433", "serial_port": "/dev/ttyUSB0", "serial_baud": 115200},
                    {"label": "868", "serial_port": "/dev/ttyUSB1"},
                ],
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["restart_required"])
        self.assertEqual(len(self.config.capture.serial), 2)
        self.assertEqual(self.config.capture.serial[0].label, "433")
        self.assertIn("serial", self.config.capture.sources)
        save_mock.assert_called_once()

    @patch("src.api.routes.system_config_routes.save_section_to_yaml")
    def test_blank_rows_are_dropped(self, save_mock):
        resp = self.client.put(
            "/api/config/capture/serial-devices",
            json={
                "enable_source": True,
                "devices": [
                    {"label": "Heltec", "serial_port": "/dev/ttyACM1"},
                    {"label": "", "serial_port": None},
                    {"label": "auto", "serial_port": "  "},
                ],
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(self.config.capture.serial), 1)
        self.assertEqual(self.config.capture.serial[0].label, "Heltec")
        self.assertEqual(self.config.capture.serial_port, "/dev/ttyACM1")
        payload = save_mock.call_args[0][1]
        self.assertEqual(len(payload["serial"]), 1)

    @patch("src.api.routes.system_config_routes.save_section_to_yaml")
    def test_disable_removes_serial_source(self, save_mock):
        self.config.capture.sources = ["concentrator", "serial"]
        resp = self.client.put(
            "/api/config/capture/serial-devices",
            json={"enable_source": False, "devices": []},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("serial", self.config.capture.sources)
        self.assertEqual(self.config.capture.serial, [])


if __name__ == "__main__":
    unittest.main()
