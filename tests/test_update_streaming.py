"""Streaming update apply/rollback (NDJSON) coverage."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.audit import AuditLogWriter
from src.api.audit import dependencies as audit_deps
from src.api.auth import dependencies as auth_deps
from src.api.auth.jwt_session import JwtSessionService
from src.api.routes import update_routes
from src.api.update import ReleaseChannelRegistry, UpdateApplier
from src.api.update.streaming import stream_update

_SECRET = "update-stream-secret-" + "s" * 32


class _FakeRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(
        self, args: list[str], cwd: Optional[str], timeout_seconds: float,
    ) -> tuple[int, str, str]:
        self.calls.append(list(args))
        if args[:2] == ["git", "rev-parse"]:
            return 0, "abc123\n", ""
        return 0, "ok", ""


def _parse_ndjson_body(raw: bytes) -> list[dict]:
    events = []
    for line in raw.decode("utf-8").splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return events


class TestStreamUpdateGenerator(unittest.IsolatedAsyncioTestCase):
    async def test_stream_emits_started_steps_and_result(self) -> None:
        applier = UpdateApplier(runner=_FakeRunner(), repo_path=".")
        chunks: list[bytes] = []
        async for chunk in stream_update(applier, mode="apply", branch="main"):
            chunks.append(chunk)
        events = []
        for chunk in chunks:
            events.extend(_parse_ndjson_body(chunk))
        types = [e["type"] for e in events]
        self.assertEqual(types[0], "started")
        self.assertIn("result", types)
        step_events = [e for e in events if e["type"] == "step"]
        self.assertGreaterEqual(len(step_events), 4)
        phases = {e["step"]: e["phase"] for e in step_events}
        self.assertIn("git fetch", phases)
        self.assertIn(phases["git fetch"], ("started", "completed"))


class TestUpdateStreamRoutes(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.audit = AuditLogWriter(log_path=Path(self.tmp.name) / "a.jsonl")
        self.jwt = JwtSessionService(_SECRET, expiry_minutes=60, session_version=1)
        self.applier = UpdateApplier(runner=_FakeRunner(), repo_path=".")
        update_routes.init_routes(
            applier=self.applier,
            registry=ReleaseChannelRegistry(),
        )
        auth_deps.init_auth(self.jwt)
        audit_deps.init_audit(self.audit)
        app = FastAPI()
        app.include_router(update_routes.router)
        self.client = TestClient(app)
        self.admin_token = self.jwt.issue("admin", "admin")

    def tearDown(self) -> None:
        update_routes.reset_routes()
        auth_deps.reset_auth()
        audit_deps.reset_audit()
        self.tmp.cleanup()

    def test_apply_stream_returns_ndjson_lines(self) -> None:
        self.client.cookies.set("meshpoint_session", self.admin_token)
        with self.client.stream(
            "POST",
            "/api/update/apply/stream",
            json={"channel_id": "stable"},
        ) as response:
            self.assertEqual(response.status_code, 200)
            self.assertIn("application/x-ndjson", response.headers.get("content-type", ""))
            raw = b"".join(response.iter_bytes())
        events = _parse_ndjson_body(raw)
        self.assertEqual(events[0]["type"], "started")
        self.assertEqual(events[-1]["type"], "result")
        self.assertTrue(events[-1]["result"]["success"])

    def test_apply_stream_rejects_viewer(self) -> None:
        viewer = self.jwt.issue("viewer", "viewer")
        self.client.cookies.set("meshpoint_session", viewer)
        response = self.client.post(
            "/api/update/apply/stream", json={"channel_id": "stable"},
        )
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
