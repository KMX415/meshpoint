"""GET /api/reticulum/announces (Activity tab) and GET /api/reticulum/
peers/{destination_hash}/link (Peers drawer's live routing/signal detail).

FastAPI-gated (CI / Pi only), same `_HAS_FASTAPI` pattern the other route
tests use.
"""

from __future__ import annotations

import unittest

try:
    import fastapi  # noqa: F401
    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False


@unittest.skipUnless(_HAS_FASTAPI, "routes imports fastapi (CI / Pi only)")
class TestAnnouncesRoute(unittest.TestCase):
    def setUp(self) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from apps.reticulum.backend import routes

        self._routes = routes
        routes.reset_routes()

        class _FakeService:
            def announce_log(self):
                return [
                    {"ts": "2026-09-07T12:00:00+00:00", "destination_hash": "ab",
                     "display_name": "Bob", "aspect": "lxmf.delivery"},
                ]

            def peer_link_info(self, destination_hash):
                return {
                    "hops": 3, "has_path": True, "next_hop_interface": "RNodeInterface",
                    "identity_resolved": True, "announces_this_session": 2,
                    "rssi": -72.0, "snr": 8.5, "quality": 91, "signal_at": "2026-09-07T12:00:00+00:00",
                }

        routes.init_routes(_FakeService(), object())
        app = FastAPI()
        app.include_router(routes.router)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self._routes.reset_routes()

    def test_returns_the_service_log(self) -> None:
        r = self.client.get("/api/reticulum/announces")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["display_name"], "Bob")
        self.assertEqual(body[0]["aspect"], "lxmf.delivery")

    def test_503_when_service_absent(self) -> None:
        self._routes.reset_routes()
        r = self.client.get("/api/reticulum/announces")
        self.assertEqual(r.status_code, 503)

    def test_peer_link_returns_service_data(self) -> None:
        r = self.client.get("/api/reticulum/peers/" + "aa" * 16 + "/link")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["hops"], 3)
        self.assertTrue(body["has_path"])
        self.assertEqual(body["next_hop_interface"], "RNodeInterface")
        self.assertTrue(body["identity_resolved"])
        self.assertEqual(body["announces_this_session"], 2)
        self.assertEqual(body["rssi"], -72.0)

    def test_peer_link_503_when_service_absent(self) -> None:
        self._routes.reset_routes()
        r = self.client.get("/api/reticulum/peers/" + "aa" * 16 + "/link")
        self.assertEqual(r.status_code, 503)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
