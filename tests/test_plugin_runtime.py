"""Optional plugin startup must not change core behavior when absent or broken."""
from __future__ import annotations
import tempfile
import unittest
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient
from src.config import AppConfig
from src.plugins.runtime import PluginRuntime


class TestPluginRuntime(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.config = AppConfig()

    def tearDown(self):
        self.tmp.cleanup()

    def plugin(self, name, code, *, enabled=True, provides='"routes"'):
        folder = self.root / name
        (folder / "backend").mkdir(parents=True)
        (folder / "plugin.toml").write_text(
            f'name="{name}"\nversion="1"\nmeshpoint_api=1\nprovides=[{provides}]\n',
            encoding="utf-8",
        )
        (folder / "backend" / "__init__.py").write_text(code, encoding="utf-8")
        self.config.plugins[name] = {"enabled": enabled}

    def build(self):
        app = FastAPI()
        @app.get("/api/core")
        def core():
            return {"core": True}
        runtime = PluginRuntime(self.root, self.config)
        runtime.discover()
        runtime.mount(app)
        return app, runtime

    async def test_empty_directory_preserves_core(self):
        app, runtime = self.build()
        self.assertEqual(runtime.states, {})
        self.assertEqual(TestClient(app).get("/api/core").json(), {"core": True})
        await runtime.start(None, None)
        await runtime.stop()

    async def test_disabled_plugin_is_not_imported(self):
        self.plugin("disabled", 'raise AssertionError("must not import")', enabled=False)
        _, runtime = self.build()
        self.assertEqual(runtime.states["disabled"].status, "installed")

    async def test_partial_registration_is_discarded(self):
        self.plugin("broken", """from fastapi import APIRouter
router = APIRouter()
@router.get('/api/broken')
def route(): return {}
def register(reg):
    reg.add_router(router)
    raise ValueError('failed')
""")
        app, runtime = self.build()
        self.assertEqual(runtime.states["broken"].status, "failed")
        self.assertEqual(TestClient(app).get("/api/broken").status_code, 404)
        self.assertEqual(TestClient(app).get("/api/core").status_code, 200)

    async def test_plugin_routes_require_authentication(self):
        self.plugin("secure", """from fastapi import APIRouter
router = APIRouter()
@router.get('/api/secure')
def route(): return {}
def register(reg): reg.add_router(router)
""")
        app, runtime = self.build()
        self.assertEqual(runtime.states["secure"].status, "loaded")
        self.assertEqual(TestClient(app).get("/api/secure").status_code, 401)
        other = PluginRuntime(self.root / "empty", AppConfig())
        other.discover()
        second = FastAPI()
        other.mount(second)
        self.assertEqual(TestClient(second).get("/api/secure").status_code, 404)

    async def test_failed_service_is_cleaned_up(self):
        self.plugin("service", """class Service:
    async def start(self): raise RuntimeError('start failed')
    async def stop(self): self.stopped = True
service = Service()
def register(reg): reg.add_service('test', lambda ctx: service)
""", provides='"service"')
        _, runtime = self.build()
        registration = runtime.states["service"].registration
        service = registration.services[0][1](None)
        await runtime.start(None, None)
        self.assertTrue(service.stopped)
        self.assertEqual(runtime.states["service"].status, "failed")
        self.assertFalse(runtime.live)


if __name__ == "__main__":
    unittest.main()
