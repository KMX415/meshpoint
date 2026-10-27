"""GET/PUT/DELETE /api/reticulum/contacts + petname enrichment on
/peers and /announces.

FastAPI-gated (CI / Pi only), same `_HAS_FASTAPI` pattern the other route
tests use.
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


@unittest.skipUnless(_HAS_FASTAPI, "routes imports fastapi (CI / Pi only)")
class TestContactsRoute(unittest.TestCase):
    def setUp(self) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from src.api.auth.jwt_session import ROLE_ADMIN, SessionClaims
        from src.api.auth.dependencies import require_admin
        from apps.reticulum.backend import routes
        from apps.reticulum.backend.contacts import ContactStore

        self._routes = routes
        routes.reset_routes()

        self._tmp = tempfile.TemporaryDirectory()

        class _FakePeer:
            def __init__(self, h, name, aspect):
                self._h, self._name, self._aspect = h, name, aspect

            def to_dict(self):
                return {
                    "destination_hash": self._h, "display_name": self._name,
                    "aspect": self._aspect, "first_seen": "x", "last_seen": "y",
                }

        class _FakeService:
            async def list_peers(self):
                return [
                    _FakePeer("h1", "AnnouncedName", "lxmf.delivery"),
                    _FakePeer("h2", "Other", "nomadnetwork.node"),
                ]

            def announce_log(self):
                return [
                    {"ts": "t", "destination_hash": "h1", "display_name": "AnnouncedName",
                     "aspect": "lxmf.delivery"},
                ]

        routes.init_routes(_FakeService(), object())
        # Point the store at a temp file instead of data/reticulum/.
        routes._contacts = ContactStore(Path(self._tmp.name) / "contacts.json")

        app = FastAPI()
        app.dependency_overrides[require_admin] = lambda: SessionClaims(
            subject="admin", role=ROLE_ADMIN, session_version=1,
        )
        app.include_router(routes.router)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self._routes.reset_routes()
        self._tmp.cleanup()

    def test_crud_roundtrip(self) -> None:
        self.assertEqual(self.client.get("/api/reticulum/contacts").json(), {})

        r = self.client.put("/api/reticulum/contacts/h1", json={
            "petname": "Philster", "note": "voice peer", "trusted": True,
        })
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "saved")

        contacts = self.client.get("/api/reticulum/contacts").json()
        self.assertEqual(contacts["h1"]["petname"], "Philster")
        self.assertTrue(contacts["h1"]["trusted"])

        r = self.client.delete("/api/reticulum/contacts/h1")
        self.assertEqual(r.json()["status"], "removed")
        self.assertEqual(self.client.get("/api/reticulum/contacts").json(), {})

    def test_blank_petname_is_a_delete(self) -> None:
        self.client.put("/api/reticulum/contacts/h1", json={"petname": "Bob"})
        r = self.client.put("/api/reticulum/contacts/h1", json={"petname": "   "})
        self.assertEqual(r.json()["status"], "removed")
        self.assertEqual(self.client.get("/api/reticulum/contacts").json(), {})

    def test_overlong_petname_is_400(self) -> None:
        r = self.client.put("/api/reticulum/contacts/h1", json={"petname": "x" * 65})
        self.assertEqual(r.status_code, 422)  # pydantic max_length

    def test_peers_are_enriched_with_petname(self) -> None:
        self.client.put("/api/reticulum/contacts/h1", json={
            "petname": "Philster", "trusted": True,
        })
        peers = {p["destination_hash"]: p for p in self.client.get("/api/reticulum/peers").json()}
        self.assertEqual(peers["h1"]["petname"], "Philster")
        self.assertTrue(peers["h1"]["trusted"])
        self.assertNotIn("petname", peers["h2"])  # no contact -> no key

    def test_announces_are_enriched_with_petname(self) -> None:
        self.client.put("/api/reticulum/contacts/h1", json={"petname": "Philster"})
        log = self.client.get("/api/reticulum/announces").json()
        self.assertEqual(log[0]["petname"], "Philster")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
