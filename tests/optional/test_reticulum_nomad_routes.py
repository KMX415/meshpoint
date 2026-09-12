"""Route tests for the Pages-tab endpoints in backend/nomad_routes.py.

Needs FastAPI (CI / Pi only -- the dev Mac has no fastapi), mirrors
tests/test_plugin_loader.py's own ``_HAS_FASTAPI`` gate. The file layer
these wrap is covered FastAPI-free by test_node_pages.py.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    import fastapi  # noqa: F401
    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False

from apps.reticulum.backend import state


@unittest.skipUnless(_HAS_FASTAPI, "nomad_routes imports fastapi (CI / Pi only)")
class TestNodePagesRoutes(unittest.TestCase):
    def setUp(self) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from src.api.auth.dependencies import require_admin
        from src.api.auth.jwt_session import ROLE_ADMIN, SessionClaims

        from apps.reticulum.backend import nomad_routes

        self._tmp = tempfile.TemporaryDirectory()
        self.pages_dir = str(Path(self._tmp.name) / "pages")
        state.init({"node_enabled": True, "node_pages_dir": self.pages_dir})
        nomad_routes.reset_routes()  # _service stays None -> reload is a no-op

        app = FastAPI()
        app.dependency_overrides[require_admin] = lambda: SessionClaims(
            subject="admin", role=ROLE_ADMIN, session_version=1,
        )
        app.include_router(nomad_routes.router)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        from apps.reticulum.backend import nomad_routes

        nomad_routes.reset_routes()
        state.init({})
        self._tmp.cleanup()

    def test_list_is_empty_but_lists_index(self) -> None:
        body = self.client.get("/api/reticulum/nomad/pages").json()
        self.assertEqual([p["name"] for p in body["pages"]], ["index.mu"])
        self.assertFalse(body["pages"][0]["exists"])
        self.assertEqual(body["pages_dir"], self.pages_dir)
        self.assertFalse(body["node_hosting"])  # _service is None

    def test_put_then_get_roundtrips_and_reports_not_served(self) -> None:
        r = self.client.put(
            "/api/reticulum/nomad/pages/index.mu", json={"content": "`!hi`!"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["saved"])
        self.assertFalse(r.json()["served"])  # no running node
        got = self.client.get("/api/reticulum/nomad/pages/index.mu").json()
        self.assertEqual(got["content"], "`!hi`!")

    def test_put_reserved_name_is_400(self) -> None:
        r = self.client.put(
            "/api/reticulum/nomad/pages/info.mu", json={"content": "x"},
        )
        self.assertEqual(r.status_code, 400)

    def test_get_bad_name_is_400(self) -> None:
        r = self.client.get("/api/reticulum/nomad/pages/not-a-page")
        self.assertEqual(r.status_code, 400)

    def test_delete_removes_the_file(self) -> None:
        self.client.put(
            "/api/reticulum/nomad/pages/about.mu", json={"content": "x"},
        )
        r = self.client.delete("/api/reticulum/nomad/pages/about.mu")
        self.assertEqual(r.status_code, 200)
        names = [p["name"] for p in self.client.get(
            "/api/reticulum/nomad/pages").json()["pages"]]
        self.assertNotIn("about.mu", names)

    def test_sample_page_returns_content(self) -> None:
        body = self.client.get("/api/reticulum/nomad/sample-page").json()
        self.assertTrue(body["content"].strip())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
