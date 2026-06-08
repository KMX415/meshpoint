"""Configurable outbound HTTP webhooks for mesh events (PR 10).

Rules are defined in ``local.yaml`` under ``webhooks``. Each matching event
schedules a non-blocking POST via httpx; failures are logged to the audit log
and never propagate to the packet pipeline.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Optional
from urllib.parse import urlparse

from src.models.packet import Packet, PacketType

if TYPE_CHECKING:
    from src.api.audit.audit_log import AuditLogWriter
    from src.config import WebhookConfig, WebhookRuleConfig
    from src.relay.relay_manager import RelayManager
    from src.storage.node_repository import NodeRepository

logger = logging.getLogger(__name__)

POLL_INTERVAL_SECONDS = 60.0
DEFAULT_HTTP_TIMEOUT_SECONDS = 10.0
ONLINE_THRESHOLD = timedelta(hours=2)

VALID_EVENTS = frozenset({
    "battery_low",
    "node_offline",
    "node_online",
    "keyword_match",
    "duty_spike",
    "storm_quarantine",
})

# Reserved for PR 12 — rules validate but do not fire until wired.
_DEFERRED_EVENTS = frozenset({"storm_quarantine"})

TEST_PAYLOAD_MESSAGE = (
    "Meshpoint webhook test — dummy payload, not a real mesh event"
)


@dataclass
class LastFireRecord:
    fired_at: datetime
    result: str
    status_code: int | None = None
    is_test: bool = False
    error: str | None = None


def build_webhook_payload(
    event: str,
    *,
    rule_name: str,
    device_name: str,
    node_id: str = "",
    data: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """JSON body for outbound webhook POSTs (no secrets)."""
    payload: dict[str, Any] = {
        "event": event,
        "rule": rule_name,
        "device_name": device_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if node_id:
        payload["node_id"] = node_id
    if data:
        payload["data"] = data
    return payload


class WebhookEngine:
    """Evaluates webhook rules and fires async HTTP POSTs."""

    def __init__(
        self,
        config: WebhookConfig,
        device_name: str,
        node_repo: NodeRepository,
        relay_manager: RelayManager,
        audit: AuditLogWriter,
        *,
        poll_interval_seconds: float = POLL_INTERVAL_SECONDS,
    ) -> None:
        self._config = config
        self._device_name = device_name or "Meshpoint"
        self._node_repo = node_repo
        self._relay = relay_manager
        self._audit = audit
        self._poll_interval = poll_interval_seconds
        self._rules_by_event: dict[str, list[WebhookRuleConfig]] = {}
        self._cooldown_until: dict[str, datetime] = {}
        self._online_state: dict[str, bool] = {}
        self._last_duty_percent: float | None = None
        self._poll_task: asyncio.Task | None = None
        self._started = False
        self._last_fired: dict[str, LastFireRecord] = {}
        self._index_rules()

    def _index_rules(self) -> None:
        self._rules_by_event.clear()
        if not self._config.enabled:
            return
        for rule in self._config.rules:
            if not rule.enabled or rule.event in _DEFERRED_EVENTS:
                continue
            self._rules_by_event.setdefault(rule.event, []).append(rule)

    async def start(self) -> None:
        if self._started or not self._config.enabled:
            return
        self._started = True
        await self._refresh_online_state()
        self._poll_task = asyncio.get_running_loop().create_task(self._poll_loop())
        logger.info(
            "Webhook engine started (%d active rules)",
            sum(len(v) for v in self._rules_by_event.values()),
        )

    async def stop(self) -> None:
        self._started = False
        if self._poll_task is not None:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None

    def get_status(self) -> dict[str, Any]:
        """Safe status snapshot for the dashboard (no full URLs or secrets)."""
        rules_out: list[dict[str, Any]] = []
        for rule in self._config.rules:
            last = self._last_fired.get(rule.name)
            entry: dict[str, Any] = {
                "name": rule.name,
                "event": rule.event,
                "enabled": rule.enabled,
                "active": (
                    self._config.enabled
                    and rule.enabled
                    and rule.event not in _DEFERRED_EVENTS
                ),
                "deferred": rule.event in _DEFERRED_EVENTS,
                "url_host": _url_host(rule.url),
                "cooldown_seconds": rule.cooldown_seconds,
                "last_fired_at": last.fired_at.isoformat() if last else None,
                "last_result": last.result if last else None,
                "last_status_code": last.status_code if last else None,
                "last_was_test": last.is_test if last else None,
                "last_error": last.error if last else None,
            }
            if rule.event == "keyword_match" and rule.keyword:
                entry["keyword"] = rule.keyword
            if rule.event == "battery_low":
                entry["battery_threshold_percent"] = rule.battery_threshold_percent
            if rule.event == "duty_spike":
                entry["duty_threshold_percent"] = rule.duty_threshold_percent
            rules_out.append(entry)
        return {
            "enabled": self._config.enabled,
            "engine_running": self._started,
            "rules": rules_out,
        }

    async def fire_test(self, rule_name: str) -> dict[str, Any]:
        """Send a clearly marked dummy POST to verify connectivity."""
        rule = self._find_rule(rule_name)
        if rule is None:
            raise ValueError(f"unknown webhook rule: {rule_name}")
        body = build_webhook_payload(
            "test",
            rule_name=rule.name,
            device_name=self._device_name,
            data={
                "test": True,
                "message": TEST_PAYLOAD_MESSAGE,
            },
        )
        return await self._post_rule(rule, body, is_test=True)

    def _find_rule(self, name: str) -> WebhookRuleConfig | None:
        target = (name or "").strip()
        for rule in self._config.rules:
            if rule.name == target:
                return rule
        return None

    def on_packet(self, packet: Packet) -> None:
        """Sync pipeline hook; schedules async evaluation."""
        if not self._started:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._handle_packet(packet))

    async def _handle_packet(self, packet: Packet) -> None:
        source = (packet.source_id or "").strip()
        if not source:
            return

        was_online = self._online_state.get(source)
        if was_online is False:
            await self._fire_event(
                "node_online",
                node_id=source,
                data=self._node_data_from_packet(packet, source),
            )
        self._online_state[source] = True

        if packet.packet_type == PacketType.TELEMETRY and packet.decoded_payload:
            battery = packet.decoded_payload.get("battery_level")
            if battery is not None:
                await self._evaluate_battery_low(
                    source, float(battery), packet,
                )

        if packet.packet_type == PacketType.TEXT:
            text = _packet_text(packet)
            if text:
                await self._evaluate_keyword_match(source, text, packet)

    async def _poll_loop(self) -> None:
        try:
            while self._started:
                await asyncio.sleep(self._poll_interval)
                await self._check_offline_transitions()
                await self._check_duty_spike()
        except asyncio.CancelledError:
            pass

    async def _check_offline_transitions(self) -> None:
        if "node_offline" not in self._rules_by_event:
            return
        nodes = await self._node_repo.get_all()
        now = datetime.now(timezone.utc)
        for node in nodes:
            online = is_node_online(node.last_heard, now=now)
            was_online = self._online_state.get(node.node_id)
            if was_online is True and not online:
                await self._fire_event(
                    "node_offline",
                    node_id=node.node_id,
                    data={
                        "long_name": node.long_name or node.short_name or node.node_id,
                        "last_heard": node.last_heard,
                        "offline_hours": round(
                            ONLINE_THRESHOLD.total_seconds() / 3600, 1
                        ),
                    },
                )
            self._online_state[node.node_id] = online

    async def _check_duty_spike(self) -> None:
        if "duty_spike" not in self._rules_by_event:
            return
        stats = self._relay.get_stats()
        budget = stats.get("channel_budget") or {}
        usage = float(budget.get("relay_total_usage_percent") or 0.0)
        self._last_duty_percent = usage
        for rule in self._rules_by_event["duty_spike"]:
            if usage < rule.duty_threshold_percent:
                continue
            if not self._cooldown_elapsed(rule, key="duty"):
                continue
            self._mark_cooldown(rule, key="duty")
            await self._post_rule(
                rule,
                build_webhook_payload(
                    "duty_spike",
                    rule_name=rule.name,
                    device_name=self._device_name,
                    data={
                        "relay_usage_percent": usage,
                        "threshold_percent": rule.duty_threshold_percent,
                    },
                ),
            )

    async def _evaluate_battery_low(
        self, node_id: str, battery: float, packet: Packet
    ) -> None:
        rules = self._rules_by_event.get("battery_low") or []
        for rule in rules:
            if battery > rule.battery_threshold_percent:
                continue
            if not self._cooldown_elapsed(rule, key=node_id):
                continue
            self._mark_cooldown(rule, key=node_id)
            await self._post_rule(
                rule,
                build_webhook_payload(
                    "battery_low",
                    rule_name=rule.name,
                    device_name=self._device_name,
                    node_id=node_id,
                    data={
                        "battery_level": int(round(battery)),
                        **self._node_data_from_packet(packet, node_id),
                    },
                ),
            )

    async def _evaluate_keyword_match(
        self, node_id: str, text: str, packet: Packet
    ) -> None:
        rules = self._rules_by_event.get("keyword_match") or []
        for rule in rules:
            keyword = (rule.keyword or "").strip()
            if not keyword or keyword.lower() not in text.lower():
                continue
            if not self._cooldown_elapsed(rule, key=node_id):
                continue
            self._mark_cooldown(rule, key=node_id)
            await self._post_rule(
                rule,
                build_webhook_payload(
                    "keyword_match",
                    rule_name=rule.name,
                    device_name=self._device_name,
                    node_id=node_id,
                    data={
                        "keyword": keyword,
                        "text_preview": text[:200],
                        **self._node_data_from_packet(packet, node_id),
                    },
                ),
            )

    async def _fire_event(
        self,
        event: str,
        *,
        node_id: str,
        data: dict[str, Any],
    ) -> None:
        for rule in self._rules_by_event.get(event) or []:
            if not self._cooldown_elapsed(rule, key=node_id):
                continue
            self._mark_cooldown(rule, key=node_id)
            await self._post_rule(
                rule,
                build_webhook_payload(
                    event,
                    rule_name=rule.name,
                    device_name=self._device_name,
                    node_id=node_id,
                    data=data,
                ),
            )

    async def _post_rule(
        self,
        rule: WebhookRuleConfig,
        body: dict[str, Any],
        *,
        is_test: bool = False,
    ) -> dict[str, Any]:
        host = _url_host(rule.url)
        started = datetime.now(timezone.utc)
        audit_action = "webhook.test" if is_test else "webhook.fire"
        try:
            import httpx

            async with httpx.AsyncClient(
                timeout=DEFAULT_HTTP_TIMEOUT_SECONDS,
            ) as client:
                response = await client.post(rule.url, json=body)
            duration_ms = int(
                (datetime.now(timezone.utc) - started).total_seconds() * 1000
            )
            ok = 200 <= response.status_code < 300
            error = None if ok else f"HTTP {response.status_code}"
            self._record_last_fire(
                rule.name,
                result="success" if ok else "error",
                status_code=response.status_code,
                is_test=is_test,
                error=error,
            )
            self._audit.write(
                user="system",
                action=audit_action,
                params={
                    "rule": rule.name,
                    "event": body.get("event"),
                    "url_host": host,
                    "status_code": response.status_code,
                    "node_id": body.get("node_id", ""),
                    "test": is_test,
                },
                result="success" if ok else "error",
                duration_ms=duration_ms,
                error=error,
            )
            if not ok:
                logger.warning(
                    "Webhook %s returned HTTP %s",
                    rule.name,
                    response.status_code,
                )
            return {
                "rule": rule.name,
                "test": is_test,
                "result": "success" if ok else "error",
                "status_code": response.status_code,
                "url_host": host,
                "error": error,
            }
        except Exception as exc:
            duration_ms = int(
                (datetime.now(timezone.utc) - started).total_seconds() * 1000
            )
            err_text = str(exc) or exc.__class__.__name__
            self._record_last_fire(
                rule.name,
                result="error",
                status_code=None,
                is_test=is_test,
                error=err_text,
            )
            self._audit.write(
                user="system",
                action=audit_action,
                params={
                    "rule": rule.name,
                    "event": body.get("event"),
                    "url_host": host,
                    "node_id": body.get("node_id", ""),
                    "test": is_test,
                },
                result="error",
                duration_ms=duration_ms,
                error=err_text,
            )
            logger.warning("Webhook %s failed: %s", rule.name, exc)
            return {
                "rule": rule.name,
                "test": is_test,
                "result": "error",
                "status_code": None,
                "url_host": host,
                "error": err_text,
            }

    def _record_last_fire(
        self,
        rule_name: str,
        *,
        result: str,
        status_code: int | None,
        is_test: bool,
        error: str | None,
    ) -> None:
        self._last_fired[rule_name] = LastFireRecord(
            fired_at=datetime.now(timezone.utc),
            result=result,
            status_code=status_code,
            is_test=is_test,
            error=error,
        )

    def _cooldown_elapsed(self, rule: WebhookRuleConfig, *, key: str) -> bool:
        cooldown_key = f"{rule.name}:{key}"
        until = self._cooldown_until.get(cooldown_key)
        if until is None:
            return True
        return datetime.now(timezone.utc) >= until

    def _mark_cooldown(self, rule: WebhookRuleConfig, *, key: str) -> None:
        cooldown_key = f"{rule.name}:{key}"
        seconds = max(0.0, float(rule.cooldown_seconds))
        self._cooldown_until[cooldown_key] = (
            datetime.now(timezone.utc) + timedelta(seconds=seconds)
        )

    async def _refresh_online_state(self) -> None:
        nodes = await self._node_repo.get_all()
        now = datetime.now(timezone.utc)
        for node in nodes:
            self._online_state[node.node_id] = is_node_online(
                node.last_heard, now=now
            )

    @staticmethod
    def _node_data_from_packet(packet: Packet, node_id: str) -> dict[str, Any]:
        payload = packet.decoded_payload or {}
        return {
            "long_name": payload.get("long_name")
            or payload.get("short_name")
            or node_id,
        }


def _packet_text(packet: Packet) -> str:
    payload = packet.decoded_payload or {}
    for key in ("text", "message", "body"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def is_node_online(
    last_heard: str | datetime | None, *, now: datetime | None = None
) -> bool:
    """True when the node was heard within ONLINE_THRESHOLD."""
    heard = _parse_last_heard(last_heard)
    if heard is None:
        return False
    ref = now or datetime.now(timezone.utc)
    return (ref - heard) < ONLINE_THRESHOLD


def _parse_last_heard(raw: str | datetime | None) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    try:
        text = raw.replace(" ", "T")
        if not text.endswith("Z") and "+" not in text:
            text += "Z"
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _url_host(url: str) -> str:
    try:
        parsed = urlparse(url)
        return parsed.hostname or url
    except Exception:
        return "unknown"
