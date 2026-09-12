"""Catalog auth, pinning and disabled installation with mocked network I/O."""
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.routes import plugin_source_routes
from src.api.auth import dependencies as auth
from src.api.auth.jwt_session import JwtSessionService
from src.api.audit import AuditLogWriter
from src.api.audit import dependencies as audit
from src.config import AppConfig
from src.plugins.runtime import PluginRuntime

URL = "https://github.com/example/catalog"
SHA = "a" * 40
ENTRY = {"id":"hello-service", "kind":"app", "provides":["service"], "compatible":True}
CATALOG = {"owner":"example", "repo":"catalog", "plugins":[ENTRY], "themes":[]}


class TestPluginSourceRoutes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.runtime = PluginRuntime(root / "apps", AppConfig(plugin_sources_enabled=True))
        self.jwt = JwtSessionService("test-source-" + "x" * 32, expiry_minutes=60, session_version=1)
        auth.init_auth(self.jwt)
        audit.init_audit(AuditLogWriter(root / "audit.jsonl"))
        app = FastAPI()
        app.include_router(plugin_source_routes.build_router(self.runtime))
        self.client = TestClient(app)
        self.persist = patch.object(plugin_source_routes, "save_section_to_yaml").start()
        self.resolve = patch.object(plugin_source_routes.sources, "resolve_commit", return_value={"sha":SHA}).start()
        self.catalog = patch.object(plugin_source_routes.sources, "fetch_catalog", return_value=CATALOG).start()
        self.install = patch.object(plugin_source_routes.installer, "install_from_source", return_value={"id":"hello-service"}).start()

    def tearDown(self):
        patch.stopall()
        auth.reset_auth()
        audit.reset_audit()
        self.tmp.cleanup()

    def login(self, role="admin"):
        self.client.cookies.set("meshpoint_session", self.jwt.issue(role, role))

    def add(self):
        return self.client.post("/api/plugin-sources", json={"url":URL,"trusted":True})

    def test_requires_admin(self):
        self.assertEqual(self.add().status_code, 401)
        self.login("viewer")
        self.assertEqual(self.add().status_code, 403)
        self.assertEqual(self.client.get("/api/plugin-sources").status_code, 403)
        self.assertEqual(self.client.post("/api/plugin-sources/install",json={"source":URL,"id":"hello-service"}).status_code,403)
        self.resolve.assert_not_called()

    def test_disabled_sources_block_all_mutations_before_io(self):
        self.runtime.config.plugin_sources_enabled = False
        self.runtime.config.plugins["_sources"] = {"repositories": [{"url": URL, "ref": SHA}]}
        app = FastAPI()
        app.include_router(plugin_source_routes.build_router(self.runtime))
        with TestClient(app) as client:
            client.cookies.set("meshpoint_session", self.jwt.issue("admin", "admin"))
            self.assertFalse(client.get("/api/plugin-sources").json()["sources_enabled"])
            for method, path, body in [
                ("POST", "", {"url": URL, "trusted": True}),
                ("PUT", "", {"url": URL, "trusted": True}),
                ("POST", "/install", {"source": URL, "id": "hello-service"}),
                ("POST", "/update", {"source": URL, "id": "hello-service"}),
            ]:
                with self.subTest(path=path, method=method):
                    self.assertEqual(client.request(method, "/api/plugin-sources" + path, json=body).status_code, 403)
            self.resolve.assert_not_called()
            self.catalog.assert_not_called()
            self.install.assert_not_called()
            self.persist.assert_not_called()
            self.assertEqual(client.get("/api/plugin-sources/catalog", params={"url": URL}).status_code, 200)

    def test_source_requires_trust_and_pins_commit(self):
        self.login()
        self.assertEqual(self.client.post("/api/plugin-sources",json={"url":URL}).status_code,400)
        self.resolve.assert_not_called()
        self.assertEqual(self.add().status_code,200)
        sources=self.client.get("/api/plugin-sources").json()["sources"]
        self.assertEqual(sources[0]["ref"],SHA)
        self.assertEqual(self.add().status_code,409)

    def test_install_clears_old_enablement_and_uses_pinned_sha(self):
        self.login()
        self.add()
        self.runtime.config.plugins["hello-service"]={"enabled":True,"keep":"setting"}
        result=self.client.post("/api/plugin-sources/install",json={"source":URL,"id":"hello-service"})
        self.assertEqual(result.status_code,200)
        self.assertIs(self.runtime.config.plugins["hello-service"]["enabled"],False)
        self.assertEqual(self.runtime.config.plugins["hello-service"]["keep"],"setting")
        self.assertEqual(self.install.call_args.args[2],SHA)

    def test_persistence_failure_prevents_install(self):
        self.login()
        self.add()
        self.persist.side_effect=PermissionError("denied")
        result=self.client.post("/api/plugin-sources/install",json={"source":URL,"id":"hello-service"})
        self.assertEqual(result.status_code,500)
        self.install.assert_not_called()

    def test_cannot_overwrite_existing_plugin(self):
        self.login()
        self.add()
        (self.runtime.apps_dir / "hello-service").mkdir(parents=True)
        result=self.client.post("/api/plugin-sources/install",json={"source":URL,"id":"hello-service"})
        self.assertEqual(result.status_code,409)
        self.install.assert_not_called()


if __name__ == "__main__":
    unittest.main()
