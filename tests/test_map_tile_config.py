"""Map source validation, authorization, and persistence boundaries."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.audit.audit_log import AuditLogWriter
from src.api.audit.dependencies import get_audit_writer
from src.api.routes import config_routes
from src.config import AppConfig
from tests.auth_test_helpers import override_as_admin, override_as_viewer


class TestMapTileConfig(unittest.TestCase):
    def setUp(self):
        self.previous = config_routes._config
        self.config = AppConfig()
        config_routes._config = self.config
        self.addCleanup(setattr, config_routes, "_config", self.previous)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.audit_path = Path(self.temp.name) / "audit.jsonl"
        app = FastAPI()
        app.include_router(config_routes.router)
        app.dependency_overrides[get_audit_writer] = lambda: AuditLogWriter(log_path=self.audit_path)
        override_as_admin(app)
        self.app = app
        self.client = TestClient(app)

    def test_save_publishes_tile_source_without_changing_terminal_permission(self):
        url = "/api/offline-map/tiles/test/{z}/{x}/{y}.png"
        self.config.dashboard.web_terminal_enabled = True
        with patch.object(config_routes, "save_section_to_yaml") as save:
            response = self.client.put("/api/config/dashboard", json={"map_tile_url": url})
        self.assertEqual(response.status_code, 200)
        save.assert_called_once_with("dashboard", {"map_tile_url": url})
        self.assertTrue(self.config.dashboard.web_terminal_enabled)
        self.assertFalse(response.json()["restart_required"])
        payload = self.client.get("/api/config").json()
        self.assertEqual(payload["dashboard"], {"map_tile_url": url})
        self.assertNotIn(url, self.audit_path.read_text())

    def test_rejects_invalid_urls_and_unrelated_settings(self):
        original = self.config.dashboard.map_tile_url
        bad_values = ["https://tiles.example/test.png", "//tiles.example/{z}/{x}/{y}",
                      "javascript:/{z}/{x}/{y}", "https://user:pass@tiles.example/{z}/{x}/{y}",
                      "https://tiles.example/ {z}/{x}/{y}", "/\\tiles.example/{z}/{x}/{y}",
                      "/tiles/{z}/{x}/{y}#fragment", 1, None]
        with patch.object(config_routes, "save_section_to_yaml") as save:
            for value in bad_values:
                with self.subTest(value=value):
                    response = self.client.put("/api/config/dashboard", json={"map_tile_url": value})
                    self.assertEqual(response.status_code, 422)
            response = self.client.put("/api/config/dashboard", json={
                "map_tile_url": original, "web_terminal_enabled": True,
            })
            self.assertEqual(response.status_code, 422)
            save.assert_not_called()
        self.assertEqual(self.config.dashboard.map_tile_url, original)

    def test_disk_failure_preserves_live_configuration(self):
        original = self.config.dashboard.map_tile_url
        with patch.object(config_routes, "save_section_to_yaml", side_effect=OSError("disk full")):
            response = self.client.put("/api/config/dashboard", json={
                "map_tile_url": "https://tiles.example/{z}/{x}/{y}.png",
            })
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.config.dashboard.map_tile_url, original)

    def test_viewer_can_read_but_cannot_change_source(self):
        override_as_viewer(self.app)
        self.assertIn("dashboard", self.client.get("/api/config").json())
        with patch.object(config_routes, "save_section_to_yaml") as save:
            response = self.client.put("/api/config/dashboard", json={
                "map_tile_url": "/tiles/{z}/{x}/{y}.png",
            })
            self.assertEqual(response.status_code, 403)
            save.assert_not_called()
