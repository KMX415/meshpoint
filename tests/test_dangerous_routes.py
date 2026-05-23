"""Route-level coverage for the Settings → Dangerous endpoints."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.audit import AuditLogWriter
from src.api.audit import dependencies as audit_deps
from src.api.auth import dependencies as auth_deps
from src.api.auth.jwt_session import JwtSessionService
from src.api.dangerous.actions import (
    DangerousAction,
    DangerousActionRegistry,
    DangerousActionResult,
)
from src.api.routes import dangerous_routes

_SECRET = "dangerous-routes-secret-" + "d" * 32


def _build_registry() -> DangerousActionRegistry:
    success = DangerousAction(
        id="restart_service",
        label="Restart service",
        description="…",
        confirmation_text="restart",
        handler=lambda: DangerousActionResult(success=True, message="ok"),
    )
    failure = DangerousAction(
        id="will_fail",
        label="Always fails",
        description="…",
        confirmation_text="fail",
        handler=lambda: DangerousActionResult(success=False, message="nope"),
    )
    return DangerousActionRegistry([success, failure])


class TestDangerousRoutes(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.audit_path = Path(self.tmp.name) / "audit.jsonl"
        self.audit = AuditLogWriter(log_path=self.audit_path)
        self.jwt = JwtSessionService(_SECRET, expiry_minutes=60, session_version=1)
        dangerous_routes.init_routes(_build_registry())
        auth_deps.init_auth(self.jwt)
        audit_deps.init_audit(self.audit)
        app = FastAPI()
        app.include_router(dangerous_routes.router)
        self.client = TestClient(app)
        self.admin_token = self.jwt.issue("admin", "admin")
        self.viewer_token = self.jwt.issue("viewer", "viewer")

    def tearDown(self) -> None:
        dangerous_routes.reset_routes()
        auth_deps.reset_auth()
        audit_deps.reset_audit()
        self.tmp.cleanup()

    def _audit(self) -> list[dict]:
        if not self.audit_path.exists():
            return []
        return [json.loads(line) for line in self.audit_path.read_text().splitlines() if line]

    def test_actions_listed_for_admin(self) -> None:
        self.client.cookies.set("meshpoint_session", self.admin_token)
        response = self.client.get("/api/dangerous/actions")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        ids = {a["id"] for a in body["actions"]}
        self.assertIn("restart_service", ids)
        self.assertIn("will_fail", ids)

    def test_actions_rejects_viewer(self) -> None:
        self.client.cookies.set("meshpoint_session", self.viewer_token)
        response = self.client.get("/api/dangerous/actions")
        self.assertEqual(response.status_code, 403)

    def test_invoke_runs_action_and_writes_audit(self) -> None:
        self.client.cookies.set("meshpoint_session", self.admin_token)
        response = self.client.post(
            "/api/dangerous/invoke", json={"action_id": "restart_service"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        records = self._audit()
        self.assertTrue(
            any(r["action"] == "dangerous.restart_service" for r in records)
        )

    def test_invoke_unknown_returns_404(self) -> None:
        self.client.cookies.set("meshpoint_session", self.admin_token)
        response = self.client.post(
            "/api/dangerous/invoke", json={"action_id": "no_such_action"},
        )
        self.assertEqual(response.status_code, 404)

    def test_invoke_failure_records_error_in_audit(self) -> None:
        self.client.cookies.set("meshpoint_session", self.admin_token)
        response = self.client.post(
            "/api/dangerous/invoke", json={"action_id": "will_fail"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["success"])
        records = self._audit()
        target = next(
            (r for r in records if r["action"] == "dangerous.will_fail"), None
        )
        self.assertIsNotNone(target)
        self.assertEqual(target["result"], "error")


if __name__ == "__main__":
    unittest.main()
