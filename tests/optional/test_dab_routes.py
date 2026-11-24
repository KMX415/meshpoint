"""Tests for POST /api/dab/scan/stream.

Covers the two things genuinely new in this route: sdr_registry
integration (claims/releases the dongle around the scan, rejects
cleanly with 503 if another listener already holds it -- the scan
script itself knows nothing about the registry, so this route claims
on its behalf) and request-driven command construction (--channels/
--timeout/--new). The actual subprocess is mocked (via
routes._stream_subprocess) rather than really run -- same
"needs a live process, not exercised here" scope as this repo's other
subprocess-streaming routes (Meshtastic/MeshCore/POCSAG firmware
flash), which have no tests of their own either.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.auth.dependencies import require_admin, require_auth
from src.api.auth.jwt_session import ROLE_ADMIN, SessionClaims
from src.audio import sdr_registry

from apps.dab.backend import routes as dab_routes


def _build_app() -> FastAPI:
    app = FastAPI()
    app.include_router(dab_routes.router)
    app.dependency_overrides[require_admin] = lambda: SessionClaims("test-admin", ROLE_ADMIN, 1)
    app.dependency_overrides[require_auth] = lambda: SessionClaims("test-admin", ROLE_ADMIN, 1)
    return app


async def _fake_stream_subprocess_ok(cmd):
    yield (json.dumps({"type": "started", "cmd": cmd}) + "\n").encode()
    yield (json.dumps({"type": "line", "stream": "stdout", "text": "[1/1] 7D ... FOUND"}) + "\n").encode()
    yield (json.dumps({"type": "result", "result": {"returncode": 0, "success": True}}) + "\n").encode()


async def _fake_stream_subprocess_fail(cmd):
    yield (json.dumps({"type": "started", "cmd": cmd}) + "\n").encode()
    yield (json.dumps({"type": "result", "result": {"returncode": 1, "success": False}}) + "\n").encode()


class DabScanStreamTest(unittest.TestCase):
    def setUp(self) -> None:
        sdr_registry._owner = None
        self.app = _build_app()
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        sdr_registry._owner = None

    def _parse_ndjson(self, response) -> list[dict]:
        return [json.loads(line) for line in response.text.strip().splitlines() if line.strip()]

    def test_503_when_dongle_already_claimed_by_another_listener(self):
        sdr_registry.claim("rtl433")
        with patch.object(dab_routes, "_stream_subprocess") as mock_stream:
            res = self.client.post("/api/dab/scan/stream", json={"channels": []})
        self.assertEqual(res.status_code, 503)
        self.assertIn("rtl433", res.json()["detail"])
        mock_stream.assert_not_called()
        # A rejected claim must not have touched the registry at all.
        self.assertEqual(sdr_registry.current_owner(), "rtl433")

    def test_claims_and_releases_the_dongle_around_a_successful_scan(self):
        self.assertIsNone(sdr_registry.current_owner())
        with patch.object(dab_routes, "_stream_subprocess", _fake_stream_subprocess_ok):
            res = self.client.post("/api/dab/scan/stream", json={"channels": []})
        self.assertEqual(res.status_code, 200)
        events = self._parse_ndjson(res)
        self.assertEqual(events[-1]["result"]["success"], True)
        # Released after the stream finished -- not left holding the dongle.
        self.assertIsNone(sdr_registry.current_owner())

    def test_releases_the_dongle_even_on_a_failed_scan(self):
        with patch.object(dab_routes, "_stream_subprocess", _fake_stream_subprocess_fail):
            res = self.client.post("/api/dab/scan/stream", json={"channels": []})
        self.assertEqual(res.status_code, 200)
        events = self._parse_ndjson(res)
        self.assertEqual(events[-1]["result"]["success"], False)
        self.assertIsNone(sdr_registry.current_owner())

    def test_full_scan_omits_channels_flag(self):
        captured = {}

        async def capture_cmd(cmd):
            captured["cmd"] = cmd
            async for chunk in _fake_stream_subprocess_ok(cmd):
                yield chunk

        with patch.object(dab_routes, "_stream_subprocess", capture_cmd):
            self.client.post("/api/dab/scan/stream", json={"channels": [], "timeout": 60})
        self.assertNotIn("--channels", captured["cmd"])
        self.assertIn("--timeout", captured["cmd"])
        # Whole-number timeout is formatted plain ("60"), not "60.0" --
        # cosmetic, but the trailing ".0" was pure noise in the echoed
        # command line for the common case of a plain integer input.
        self.assertIn("60", captured["cmd"])
        self.assertNotIn("60.0", captured["cmd"])
        self.assertNotIn("--new", captured["cmd"])

    def test_specific_channels_and_discard_existing_build_the_right_flags(self):
        captured = {}

        async def capture_cmd(cmd):
            captured["cmd"] = cmd
            async for chunk in _fake_stream_subprocess_ok(cmd):
                yield chunk

        with patch.object(dab_routes, "_stream_subprocess", capture_cmd):
            self.client.post("/api/dab/scan/stream", json={
                "channels": ["7D", "8B"], "timeout": 90, "discard_existing": True,
            })
        cmd = captured["cmd"]
        channels_idx = cmd.index("--channels")
        self.assertEqual(cmd[channels_idx + 1:channels_idx + 3], ["7D", "8B"])
        self.assertIn("--new", cmd)
        self.assertIn("90", cmd)
        self.assertNotIn("90.0", cmd)

    def test_fractional_timeout_keeps_its_decimal(self):
        captured = {}

        async def capture_cmd(cmd):
            captured["cmd"] = cmd
            async for chunk in _fake_stream_subprocess_ok(cmd):
                yield chunk

        with patch.object(dab_routes, "_stream_subprocess", capture_cmd):
            self.client.post("/api/dab/scan/stream", json={"channels": [], "timeout": 45.5})
        self.assertIn("45.5", captured["cmd"])

    def test_timeout_out_of_range_is_rejected(self):
        res = self.client.post("/api/dab/scan/stream", json={"channels": [], "timeout": 500})
        self.assertEqual(res.status_code, 422)


if __name__ == "__main__":
    unittest.main()
