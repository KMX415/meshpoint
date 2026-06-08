"""Tests for outbound webhook engine (PR 10)."""
from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, MagicMock, patch

from src.api.audit.audit_log import AuditLogWriter
from src.config import WebhookConfig, WebhookRuleConfig, validate_webhook_config
from src.models.packet import Packet, PacketType, Protocol
from src.relay.relay_manager import RelayManager
from src.webhook.engine import WebhookEngine, build_webhook_payload


class TestValidateWebhookConfig(unittest.TestCase):
    def test_disabled_allows_empty_rules(self) -> None:
        validate_webhook_config(WebhookConfig(enabled=False, rules=[]))

    def test_enabled_requires_rules(self) -> None:
        with self.assertRaises(ValueError):
            validate_webhook_config(WebhookConfig(enabled=True, rules=[]))

    def test_keyword_match_requires_keyword(self) -> None:
        cfg = WebhookConfig(
            enabled=True,
            rules=[
                WebhookRuleConfig(
                    name="kw",
                    url="http://127.0.0.1/hook",
                    event="keyword_match",
                )
            ],
        )
        with self.assertRaises(ValueError):
            validate_webhook_config(cfg)

    def test_rejects_non_http_url(self) -> None:
        cfg = WebhookConfig(
            enabled=True,
            rules=[
                WebhookRuleConfig(
                    name="bad",
                    url="ftp://example.com",
                    event="node_online",
                )
            ],
        )
        with self.assertRaises(ValueError):
            validate_webhook_config(cfg)


class TestWebhookEngine(unittest.IsolatedAsyncioTestCase):
    def _engine(
        self,
        *,
        rules: list[WebhookRuleConfig],
        audit_path: Path,
    ) -> WebhookEngine:
        config = WebhookConfig(enabled=True, rules=rules)
        repo = MagicMock()
        repo.get_all = AsyncMock(return_value=[])
        relay = RelayManager(enabled=False)
        audit = AuditLogWriter(log_path=audit_path)
        return WebhookEngine(
            config,
            "Test Meshpoint",
            repo,
            relay,
            audit,
        )

    async def test_battery_low_fires_post(self) -> None:
        with TemporaryDirectory() as tmp:
            rule = WebhookRuleConfig(
                name="low-batt",
                url="http://127.0.0.1:9999/hook",
                event="battery_low",
                cooldown_seconds=0,
                battery_threshold_percent=25,
            )
            engine = self._engine(rules=[rule], audit_path=Path(tmp) / "audit.jsonl")
            await engine.start()

            mock_response = MagicMock()
            mock_response.status_code = 200
            with patch("httpx.AsyncClient") as client_cls:
                client = AsyncMock()
                client.__aenter__.return_value = client
                client.__aexit__.return_value = None
                client.post = AsyncMock(return_value=mock_response)
                client_cls.return_value = client

                packet = Packet(
                    packet_id="p1",
                    source_id="node1",
                    destination_id="broadcast",
                    protocol=Protocol.MESHTASTIC,
                    packet_type=PacketType.TELEMETRY,
                    decoded_payload={
                        "battery_level": 18,
                        "long_name": "Trail Node",
                    },
                )
                await engine._handle_packet(packet)

                client.post.assert_awaited_once()
                args, kwargs = client.post.await_args
                self.assertEqual(args[0], rule.url)
                self.assertEqual(kwargs["json"]["event"], "battery_low")
                self.assertEqual(kwargs["json"]["node_id"], "node1")

            await engine.stop()

    async def test_cooldown_suppresses_repeat_fire(self) -> None:
        with TemporaryDirectory() as tmp:
            rule = WebhookRuleConfig(
                name="low-batt",
                url="http://127.0.0.1:9999/hook",
                event="battery_low",
                cooldown_seconds=3600,
                battery_threshold_percent=25,
            )
            engine = self._engine(rules=[rule], audit_path=Path(tmp) / "audit.jsonl")
            await engine.start()

            mock_response = MagicMock()
            mock_response.status_code = 200
            with patch("httpx.AsyncClient") as client_cls:
                client = AsyncMock()
                client.__aenter__.return_value = client
                client.__aexit__.return_value = None
                client.post = AsyncMock(return_value=mock_response)
                client_cls.return_value = client

                packet = Packet(
                    packet_id="p1",
                    source_id="node1",
                    destination_id="broadcast",
                    protocol=Protocol.MESHTASTIC,
                    packet_type=PacketType.TELEMETRY,
                    decoded_payload={"battery_level": 10},
                )
                await engine._handle_packet(packet)
                await engine._handle_packet(packet)
                self.assertEqual(client.post.await_count, 1)

            await engine.stop()

    async def test_keyword_match_on_text_packet(self) -> None:
        with TemporaryDirectory() as tmp:
            rule = WebhookRuleConfig(
                name="sos",
                url="http://127.0.0.1:9999/sos",
                event="keyword_match",
                keyword="SOS",
                cooldown_seconds=0,
            )
            engine = self._engine(rules=[rule], audit_path=Path(tmp) / "audit.jsonl")
            await engine.start()

            mock_response = MagicMock()
            mock_response.status_code = 204
            with patch("httpx.AsyncClient") as client_cls:
                client = AsyncMock()
                client.__aenter__.return_value = client
                client.__aexit__.return_value = None
                client.post = AsyncMock(return_value=mock_response)
                client_cls.return_value = client

                packet = Packet(
                    packet_id="p2",
                    source_id="node2",
                    destination_id="broadcast",
                    protocol=Protocol.MESHTASTIC,
                    packet_type=PacketType.TEXT,
                    decoded_payload={"text": "Need help SOS now"},
                )
                await engine._handle_packet(packet)

                client.post.assert_awaited_once()
                body = client.post.await_args.kwargs["json"]
                self.assertEqual(body["event"], "keyword_match")
                self.assertEqual(body["data"]["keyword"], "SOS")

            await engine.stop()

    async def test_post_failure_writes_audit_error(self) -> None:
        with TemporaryDirectory() as tmp:
            audit_path = Path(tmp) / "audit.jsonl"
            rule = WebhookRuleConfig(
                name="fail",
                url="http://127.0.0.1:9999/hook",
                event="node_online",
                cooldown_seconds=0,
            )
            engine = self._engine(rules=[rule], audit_path=audit_path)
            await engine.start()
            engine._online_state["node1"] = False

            with patch("httpx.AsyncClient") as client_cls:
                client = AsyncMock()
                client.__aenter__.return_value = client
                client.__aexit__.return_value = None
                client.post = AsyncMock(side_effect=OSError("connection refused"))
                client_cls.return_value = client

                packet = Packet(
                    packet_id="p3",
                    source_id="node1",
                    destination_id="broadcast",
                    protocol=Protocol.MESHTASTIC,
                    packet_type=PacketType.NODEINFO,
                )
                await engine._handle_packet(packet)

            text = audit_path.read_text(encoding="utf-8")
            self.assertIn("webhook.fire", text)
            self.assertIn("connection refused", text)
            await engine.stop()


class TestBuildWebhookPayload(unittest.TestCase):
    def test_shape(self) -> None:
        payload = build_webhook_payload(
            "battery_low",
            rule_name="low-batt",
            device_name="Meshpoint",
            node_id="abc",
            data={"battery_level": 15},
        )
        self.assertEqual(payload["event"], "battery_low")
        self.assertEqual(payload["rule"], "low-batt")
        self.assertNotIn("psk", str(payload).lower())


if __name__ == "__main__":
    unittest.main()
