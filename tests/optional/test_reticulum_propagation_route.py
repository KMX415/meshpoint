"""GET /api/reticulum/propagation + POST .../propagation/sync[/cancel].

FastAPI-gated (CI / Pi only), same `_HAS_FASTAPI` pattern as the other
route tests.
"""

from __future__ import annotations

import unittest

try:
    import fastapi  # noqa: F401
    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False


@unittest.skipUnless(_HAS_FASTAPI, "routes imports fastapi (CI / Pi only)")
class TestPropagationRoute(unittest.TestCase):
    def setUp(self) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from src.api.auth.dependencies import require_admin
        from src.api.auth.jwt_session import ROLE_ADMIN, SessionClaims
        from apps.reticulum.backend import routes

        self._routes = routes
        routes.reset_routes()

        class _FakeService:
            def __init__(self):
                self.cancelled = False
                self.synced = False
                self.sync_ok = True

            def propagation_status(self):
                return None

            def propagation_client_status(self):
                return {
                    "outbound_node": "ab" * 16, "auto_sync_interval_s": 0,
                    "state": "idle", "progress": None, "last_result": 2,
                }

            def sync_propagation_messages(self):
                self.synced = True
                return {"ok": self.sync_ok, "error": None if self.sync_ok else "No outbound propagation node configured"}

            def cancel_propagation_sync(self):
                self.cancelled = True

        self.svc = _FakeService()
        routes.init_routes(self.svc, object())

        app = FastAPI()
        app.dependency_overrides[require_admin] = lambda: SessionClaims(
            subject="admin", role=ROLE_ADMIN, session_version=1,
        )
        app.include_router(routes.router)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self._routes.reset_routes()

    def test_get_returns_local_and_client(self) -> None:
        r = self.client.get("/api/reticulum/propagation")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIsNone(body["local"])
        self.assertEqual(body["client"]["outbound_node"], "ab" * 16)
        self.assertEqual(body["client"]["last_result"], 2)

    def test_sync_dispatches(self) -> None:
        r = self.client.post("/api/reticulum/propagation/sync")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(self.svc.synced)

    def test_sync_400_when_no_node(self) -> None:
        self.svc.sync_ok = False
        r = self.client.post("/api/reticulum/propagation/sync")
        self.assertEqual(r.status_code, 400)

    def test_cancel(self) -> None:
        r = self.client.post("/api/reticulum/propagation/sync/cancel")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(self.svc.cancelled)

    def test_503_without_service(self) -> None:
        self._routes.reset_routes()
        r = self.client.get("/api/reticulum/propagation")
        self.assertEqual(r.status_code, 503)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
