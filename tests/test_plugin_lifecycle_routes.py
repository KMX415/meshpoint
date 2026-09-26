"""Admin lifecycle, scoped assets, and update rollback use disposable files."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.api.routes import plugin_routes, plugin_asset_routes
from src.api.auth import dependencies as auth
from src.api.auth.jwt_session import JwtSessionService
from src.api.audit import AuditLogWriter
from src.api.audit import dependencies as audit
from src.config import AppConfig
from src.plugins.runtime import PluginRuntime, Registration
from src.plugins.update import replace_disabled


class TestPluginLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.folder = self.root / "apps" / "sample"
        self.folder.mkdir(parents=True)
        (self.folder / "plugin.toml").write_text(
            'name="sample"\nversion="1"\nmeshpoint_api=1\nprovides=["routes"]\n'
            '[frontend]\nscripts=["page.js"]\n', encoding="utf-8")
        (self.folder / "page.js").write_text("// declared", encoding="utf-8")
        (self.folder / "private.py").write_text("# private", encoding="utf-8")
        self.runtime = PluginRuntime(self.root / "apps", AppConfig())
        self.runtime.discover()
        self.jwt = JwtSessionService("test-lifecycle-" + "x" * 32, expiry_minutes=60, session_version=1)
        auth.init_auth(self.jwt)
        audit.init_audit(AuditLogWriter(self.root / "audit.jsonl"))
        app = FastAPI()
        app.include_router(plugin_routes.build_router(self.runtime))
        app.include_router(plugin_asset_routes.build_router(self.runtime))
        self.client = TestClient(app)
        self.persist = patch.object(plugin_routes, "save_section_to_yaml").start()

    def tearDown(self):
        patch.stopall()
        auth.reset_auth()
        audit.reset_audit()
        self.tmp.cleanup()

    def login(self, role="admin"):
        self.client.cookies.set("meshpoint_session", self.jwt.issue(role, role))

    def test_uninstall_requires_admin_and_preserves_settings_and_data(self):
        self.assertEqual(self.client.delete("/api/plugins/sample").status_code, 401)
        self.login("viewer")
        self.assertEqual(self.client.delete("/api/plugins/sample").status_code, 403)
        self.login()
        self.runtime.config.plugins["sample"] = {"enabled": False, "keep": "value"}
        retained = self.root / "capture.db"
        retained.write_text("data", encoding="utf-8")
        self.assertEqual(self.client.delete("/api/plugins/sample").status_code, 200)
        self.assertFalse(self.folder.exists())
        self.assertEqual(retained.read_text(encoding="utf-8"), "data")
        self.assertEqual(self.runtime.config.plugins["sample"]["keep"], "value")

    def test_loaded_or_enabled_plugin_cannot_be_removed(self):
        self.login()
        self.runtime.config.plugins["sample"] = {"enabled": True}
        self.assertEqual(self.client.delete("/api/plugins/sample").status_code, 409)
        self.runtime.config.plugins["sample"]["enabled"] = False
        state = self.runtime.states["sample"]
        state.registration = Registration(state.manifest, {})
        self.assertEqual(self.client.delete("/api/plugins/sample").status_code, 409)
        self.assertTrue(self.folder.exists())

    def test_inventory_includes_original_source_and_checkbox_persists(self):
        self.login()
        source = {"url": "https://github.com/example/plugins", "commit": "a" * 40}
        self.runtime.config.plugins["sample"] = {"enabled": False, "source": source, "keep": 42}
        response = self.client.put("/api/plugins/sample", json={"enabled": True})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["restart_required"])
        row = self.client.get("/api/plugins").json()["plugins"][0]
        self.assertEqual(row["source"], source)
        self.assertTrue(row["enabled"])
        self.assertEqual(self.runtime.config.plugins["sample"]["keep"], 42)

    def dependent(self, name, requires):
        folder = self.runtime.apps_dir / name
        folder.mkdir()
        (folder / "plugin.toml").write_text(f'name="{name}"\nversion="1"\nmeshpoint_api=1\n'
            f'provides=["service"]\nrequires="{requires}"\n', encoding="utf-8")
        self.runtime.discover()

    def test_dependencies_require_enabled_host_and_cascade_transitively(self):
        self.login()
        self.dependent("child", "sample")
        self.dependent("grandchild", "child")
        self.assertEqual(self.client.put("/api/plugins/child", json={"enabled": True}).status_code, 409)
        for name in ["sample", "child", "grandchild"]:
            self.assertEqual(self.client.put("/api/plugins/" + name, json={"enabled": True}).status_code, 200)
        row = next(p for p in self.client.get("/api/plugins").json()["plugins"] if p["id"] == "child")
        self.assertEqual(row["dependency"], {"id": "sample", "enabled": True})
        self.runtime.config.plugins["child"]["keep"] = "setting"
        response = self.client.put("/api/plugins/sample", json={"enabled": False})
        self.assertEqual(set(response.json()["also_disabled"]), {"child", "grandchild"})
        self.assertTrue(all(not self.runtime.config.plugins[name]["enabled"] for name in ["sample", "child", "grandchild"]))
        self.assertEqual(self.runtime.config.plugins["child"]["keep"], "setting")

    def test_failed_cascade_save_preserves_effective_settings(self):
        self.login()
        self.dependent("child", "sample")
        for name in ["sample", "child"]:
            self.runtime.config.plugins[name] = {"enabled": True}
        self.persist.side_effect = OSError("read only")
        self.assertEqual(self.client.put("/api/plugins/sample", json={"enabled": False}).status_code, 500)
        self.assertTrue(self.runtime.config.plugins["sample"]["enabled"])
        self.assertTrue(self.runtime.config.plugins["child"]["enabled"])

    def test_update_rejects_different_source_before_downloading(self):
        self.runtime.config.plugins["sample"] = {"enabled": False, "source": {"url": "original"}}
        with patch("src.plugins.update.installer.install_from_source") as download:
            with self.assertRaisesRegex(ValueError, "original source"):
                replace_disabled(self.runtime, {}, {"url": "different"}, {"id": "sample"}, self.persist)
            download.assert_not_called()
        self.assertEqual((self.folder / "page.js").read_text(encoding="utf-8"), "// declared")

    def test_assets_require_loaded_plugin_admin_and_declared_path(self):
        self.assertEqual(self.client.get("/api/plugin-ui/sample/page.js").status_code, 401)
        self.login()
        self.assertEqual(self.client.get("/api/plugin-ui/sample/page.js").status_code, 404)
        state = self.runtime.states["sample"]
        state.registration = Registration(state.manifest, {})
        state.status = "loaded"
        self.assertEqual(self.client.get("/api/plugin-ui/sample/page.js").text, "// declared")
        self.assertEqual(self.client.get("/api/plugin-ui/sample/private.py").status_code, 404)
        self.assertEqual(self.client.get("/api/plugin-ui/sample/plugin.toml").status_code, 404)
        self.login("viewer")
        self.assertEqual(self.client.get("/api/plugin-ui/sample/page.js").status_code, 403)

    def test_failed_update_restores_old_files_and_metadata(self):
        old = {"enabled": False, "source": {"url": "source", "commit": "old"}}
        self.runtime.config.plugins["sample"] = old
        def install(*args):
            (self.folder / "page.js").write_text("// new", encoding="utf-8")
            return {"id": "sample"}
        def fail(*args):
            raise OSError("disk failure")
        with patch("src.plugins.update.installer.install_from_source", side_effect=install):
            with self.assertRaises(OSError):
                replace_disabled(self.runtime, {"owner": "o", "repo": "r"},
                                 {"url": "source", "ref": "new"}, {"id": "sample"}, fail)
        self.assertEqual((self.folder / "page.js").read_text(encoding="utf-8"), "// declared")
        self.assertEqual(self.runtime.config.plugins["sample"], old)
