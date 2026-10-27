"""Theme management authorization and persistence failures."""
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.routes import theme_routes
from src.api.auth import dependencies as auth
from src.api.auth.jwt_session import JwtSessionService
from src.api.audit import AuditLogWriter
from src.api.audit import dependencies as audit
from src.config import AppConfig


class TestThemeRoutes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.config = AppConfig()
        theme_routes.init_routes(self.root / "builtin", self.root / "custom", self.config)
        self.jwt = JwtSessionService("test-theme-" + "x" * 32, expiry_minutes=60, session_version=1)
        auth.init_auth(self.jwt)
        audit.init_audit(AuditLogWriter(self.root / "audit.jsonl"))
        app = FastAPI()
        app.include_router(theme_routes.router)
        self.client = TestClient(app)
        self.payload = {"id": "custom", "label": "Custom", "css": 'html[data-theme="custom"] {--bg-primary: #123456;}'}

    def tearDown(self):
        auth.reset_auth()
        audit.reset_audit()
        theme_routes.init_routes(self.root / "none")
        self.tmp.cleanup()

    def login(self, role):
        self.client.cookies.set("meshpoint_session", self.jwt.issue(role, role))

    def test_anonymous_and_viewer_cannot_write(self):
        self.assertEqual(self.client.post("/api/themes", json=self.payload).status_code, 401)
        self.login("viewer")
        self.assertEqual(self.client.post("/api/themes", json=self.payload).status_code, 403)
        self.assertEqual(self.client.delete("/api/themes/custom").status_code, 403)
        self.assertEqual(self.client.put("/api/config/dashboard/theme", json={"theme": "dark"}).status_code, 403)

    def test_admin_save_list_delete(self):
        self.login("admin")
        self.assertEqual(self.client.post("/api/themes", json=self.payload).status_code, 200)
        ids = [row["id"] for row in self.client.get("/api/themes").json()["themes"]]
        self.assertIn("custom", ids)
        self.assertEqual(self.client.delete("/api/themes/custom").status_code, 200)
        self.assertFalse((self.root / "custom" / "custom").exists())

    def test_failed_default_save_leaves_memory_unchanged(self):
        self.login("admin")
        self.client.post("/api/themes", json=self.payload)
        with patch.object(theme_routes, "save_section_to_yaml", side_effect=PermissionError("denied")):
            result = self.client.put("/api/config/dashboard/theme", json={"theme": "custom"})
        self.assertEqual(result.status_code, 403)
        self.assertEqual(self.config.dashboard.theme, "dark")


if __name__ == "__main__":
    unittest.main()
