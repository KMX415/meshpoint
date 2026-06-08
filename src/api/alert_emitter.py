"""LAN dashboard alert broadcaster for browser push notifications (PR 04).

Emits additive WebSocket messages with ``type: "alert"`` and a payload
that includes ``event_type: "alert"`` so the frontend can show native
notifications while any authenticated dashboard tab is open.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Optional

from src.models.packet import Packet, PacketType

if TYPE_CHECKING:
    from src.api.websocket_manager import WebSocketManager
    from src.storage.node_repository import NodeRepository

logger = logging.getLogger(__name__)

# Match the dashboard node-card "recently heard" window (2 hours).
ONLINE_THRESHOLD = timedelta(hours=2)
POLL_INTERVAL_SECONDS = 60.0
BATTERY_LOW_PERCENT = 20.0
BATTERY_ALERT_COOLDOWN = timedelta(hours=1)


def build_alert_payload(
    alert_kind: str,
    *,
    node_id: str = "",
    title: str = "",
    body: str = "",
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Shape a WS alert payload (additive, non-breaking for other clients)."""
    payload: dict[str, Any] = {
        "event_type": "alert",
        "alert_kind": alert_kind,
        "node_id": node_id,
        "title": title,
        "body": body,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        payload.update(extra)
    return payload


def _parse_last_heard(raw: str | datetime | None) -> Optional[datetime]:
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


def is_node_online(last_heard: str | datetime | None, *, now: datetime | None = None) -> bool:
    """True when the node was heard within ONLINE_THRESHOLD."""
    heard = _parse_last_heard(last_heard)
    if heard is None:
        return False
    ref = now or datetime.now(timezone.utc)
    return (ref - heard) < ONLINE_THRESHOLD


class AlertEmitter:
    """Tracks node presence and emits alert WS events for the dashboard."""

    def __init__(
        self,
        node_repo: NodeRepository,
        ws_manager: WebSocketManager,
        *,
        poll_interval_seconds: float = POLL_INTERVAL_SECONDS,
    ) -> None:
        self._node_repo = node_repo
        self._ws = ws_manager
        self._poll_interval = poll_interval_seconds
        self._online_state: dict[str, bool] = {}
        self._battery_cooldown: dict[str, datetime] = {}
        self._poll_task: asyncio.Task | None = None
        self._started = False

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        await self._refresh_online_state()
        self._poll_task = asyncio.get_running_loop().create_task(self._poll_loop())
        logger.info("Alert emitter started (poll every %.0fs)", self._poll_interval)

    async def stop(self) -> None:
        self._started = False
        if self._poll_task is not None:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None

    def on_packet(self, packet: Packet) -> None:
        """Sync hook from the packet pipeline; schedules async broadcasts."""
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
            name = self._node_display_name(packet, source)
            await self._emit(
                build_alert_payload(
                    "node_online",
                    node_id=source,
                    title="Node back online",
                    body=f"{name} was heard again on the mesh.",
                )
            )
        self._online_state[source] = True

        if packet.packet_type == PacketType.TELEMETRY and packet.decoded_payload:
            battery = packet.decoded_payload.get("battery_level")
            if battery is not None and float(battery) <= BATTERY_LOW_PERCENT:
                await self._maybe_emit_battery_low(source, float(battery), packet)

    async def _maybe_emit_battery_low(
        self, node_id: str, battery: float, packet: Packet
    ) -> None:
        now = datetime.now(timezone.utc)
        last = self._battery_cooldown.get(node_id)
        if last and (now - last) < BATTERY_ALERT_COOLDOWN:
            return
        self._battery_cooldown[node_id] = now
        name = self._node_display_name(packet, node_id)
        pct = int(round(battery))
        await self._emit(
            build_alert_payload(
                "battery_low",
                node_id=node_id,
                title="Low battery",
                body=f"{name} reported {pct}% battery.",
                extra={"battery_level": pct},
            )
        )

    async def _poll_loop(self) -> None:
        try:
            while self._started:
                await asyncio.sleep(self._poll_interval)
                await self._check_offline_transitions()
        except asyncio.CancelledError:
            pass

    async def _check_offline_transitions(self) -> None:
        nodes = await self._node_repo.get_all()
        now = datetime.now(timezone.utc)
        for node in nodes:
            online = is_node_online(node.last_heard, now=now)
            was_online = self._online_state.get(node.node_id)
            if was_online is True and not online:
                name = (
                    node.long_name
                    or node.short_name
                    or node.node_id
                )
                await self._emit(
                    build_alert_payload(
                        "node_offline",
                        node_id=node.node_id,
                        title="Node offline",
                        body=f"{name} has not been heard for 2+ hours.",
                    )
                )
            self._online_state[node.node_id] = online

    async def _refresh_online_state(self) -> None:
        nodes = await self._node_repo.get_all()
        now = datetime.now(timezone.utc)
        for node in nodes:
            self._online_state[node.node_id] = is_node_online(
                node.last_heard, now=now
            )

    async def _emit(self, payload: dict[str, Any]) -> None:
        try:
            await self._ws.broadcast("alert", payload)
        except Exception:
            logger.exception("Failed to broadcast alert %s", payload.get("alert_kind"))

    @staticmethod
    def _node_display_name(packet: Packet, node_id: str) -> str:
        payload = packet.decoded_payload or {}
        return (
            payload.get("long_name")
            or payload.get("short_name")
            or node_id
        )
