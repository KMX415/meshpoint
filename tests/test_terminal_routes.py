"""Tests for the terminal HTTP routes (catalog + status).

The WebSocket endpoint is exercised separately on POSIX hosts; on
Windows we only verify the JSON contract of the static routes since
the PTY layer cannot run anyway.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.audit import AuditLogWriter
from src.api.audit import dependencies as audit_deps
from src.api.auth import dependencies as auth_deps
from src.api.auth.jwt_session import JwtSessionService
from src.api.routes import terminal_routes
from src.api.terminal.command_catalog import CommandCatalog
from src.api.terminal.pty_session import PtySession
from src.api.terminal.session_manager import SessionManager

_SECRET = "terminal-routes-secret-" + "z" * 32


class _FakePtySession(PtySession):
    """Override that skips fork() for status counting in tests."""

    def __init__(self) -> None:
        super().__init__(master_fd=-1, pid=0, shell="/bin/false")

    def terminate(self, *, grace_seconds: float = 0.5) -> None:
        self._closed = True


class TestTerminalRoutes(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.audit = AuditLogWriter(log_path=Path(self.tmp.name) / "a.jsonl")
        self.jwt = JwtSessionService(_SECRET, expiry_minutes=60, session_version=1)
        self.manager = SessionManager(max_sessions=3)
        terminal_routes.init_routes(
            session_manager=self.manager,
            command_catalog=CommandCatalog(),
            jwt_service=self.jwt,
            audit_writer=self.audit,
        )
        auth_deps.init_auth(self.jwt)
        audit_deps.init_audit(self.audit)
        app = FastAPI()
        app.include_router(terminal_routes.router)
        self.client = TestClient(app)
        self.admin_token = self.jwt.issue("admin", "admin")
        self.viewer_token = self.jwt.issue("viewer", "viewer")

    def tearDown(self) -> None:
        terminal_routes.reset_routes()
        auth_deps.reset_auth()
        audit_deps.reset_audit()
        self.tmp.cleanup()

    def test_commands_returns_payload_for_admin(self) -> None:
        self.client.cookies.set("meshpoint_session", self.admin_token)
        response = self.client.get("/api/terminal/commands")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("commands", body)
        self.assertIn("categories", body)
        self.assertGreater(len(body["commands"]), 0)

    def test_commands_rejects_anonymous(self) -> None:
        client = TestClient(self.client.app)
        response = client.get("/api/terminal/commands")
        self.assertEqual(response.status_code, 401)

    def test_commands_rejects_viewer(self) -> None:
        self.client.cookies.set("meshpoint_session", self.viewer_token)
        response = self.client.get("/api/terminal/commands")
        self.assertEqual(response.status_code, 403)

    def test_status_reports_session_counts(self) -> None:
        with mock.patch.object(
            PtySession, "spawn", side_effect=lambda **_kw: _FakePtySession()
        ):
            self.manager.spawn()
            self.client.cookies.set("meshpoint_session", self.admin_token)
            body = self.client.get("/api/terminal/status").json()
            self.assertEqual(body["active_sessions"], 1)
            self.assertEqual(body["max_sessions"], 3)


if __name__ == "__main__":
    unittest.main()
