"""Tests for webhook status and test API (PR 11)."""
from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.audit.audit_log import AuditLogWriter
from src.api.routes import webhooks_routes
from src.config import WebhookConfig, WebhookRuleConfig
from src.relay.relay_manager import RelayManager
from src.webhook.engine import TEST_PAYLOAD_MESSAGE, WebhookEngine


class TestWebhooksRoutes(unittest.TestCase):
    def _client(self, engine: WebhookEngine | None) -> TestClient:
        webhooks_routes.init_routes(engine)
        app = FastAPI()
        app.include_router(webhooks_routes.router)
        return TestClient(app)

    def test_status_without_engine(self) -> None:
        client = self._client(None)
        res = client.get("/api/webhooks/status")
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertFalse(body["enabled"])
        self.assertEqual(body["rules"], [])

    def test_status_hides_full_url(self) -> None:
        with TemporaryDirectory() as tmp:
            engine = self._engine(
                WebhookConfig(
                    enabled=True,
                    rules=[
                        WebhookRuleConfig(
                            name="ha",
                            url="http://192.168.1.10:8123/api/webhook/secret-path",
                            event="battery_low",
                        )
                    ],
                ),
                Path(tmp) / "audit.jsonl",
            )
            client = self._client(engine)
            body = client.get("/api/webhooks/status").json()
            self.assertEqual(len(body["rules"]), 1)
            rule = body["rules"][0]
            self.assertEqual(rule["url_host"], "192.168.1.10")
            self.assertNotIn("url", rule)
            self.assertNotIn("secret-path", str(body))

    def test_test_post_uses_dummy_payload(self) -> None:
        with TemporaryDirectory() as tmp:
            engine = self._engine(
                WebhookConfig(
                    enabled=False,
                    rules=[
                        WebhookRuleConfig(
                            name="probe",
                            url="http://127.0.0.1:9/hook",
                            event="node_online",
                        )
                    ],
                ),
                Path(tmp) / "audit.jsonl",
            )
            client = self._client(engine)

            mock_response = MagicMock()
            mock_response.status_code = 200
            with patch("httpx.AsyncClient") as client_cls:
                http = AsyncMock()
                http.__aenter__.return_value = http
                http.__aexit__.return_value = None
                http.post = AsyncMock(return_value=mock_response)
                client_cls.return_value = http

                res = client.post("/api/webhooks/test/probe")
                self.assertEqual(res.status_code, 200)
                body = res.json()
                self.assertTrue(body["test"])
                self.assertEqual(body["result"], "success")

                posted = http.post.await_args.kwargs["json"]
                self.assertEqual(posted["event"], "test")
                self.assertTrue(posted["data"]["test"])
                self.assertEqual(posted["data"]["message"], TEST_PAYLOAD_MESSAGE)

            status = client.get("/api/webhooks/status").json()
            self.assertIsNotNone(status["rules"][0]["last_fired_at"])
            self.assertTrue(status["rules"][0]["last_was_test"])

    def test_unknown_rule_returns_404(self) -> None:
        with TemporaryDirectory() as tmp:
            engine = self._engine(WebhookConfig(), Path(tmp) / "audit.jsonl")
            client = self._client(engine)
            res = client.post("/api/webhooks/test/missing")
            self.assertEqual(res.status_code, 404)

    @staticmethod
    def _engine(config: WebhookConfig, audit_path: Path) -> WebhookEngine:
        repo = MagicMock()
        repo.get_all = AsyncMock(return_value=[])
        return WebhookEngine(
            config,
            "Test Meshpoint",
            repo,
            RelayManager(enabled=False),
            AuditLogWriter(log_path=audit_path),
        )


if __name__ == "__main__":
    unittest.main()
