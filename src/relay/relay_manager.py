from __future__ import annotations

import asyncio
import logging
from typing import Optional

from src.models.packet import Packet, PacketType
from src.relay.dedup_filter import DeduplicationFilter
from src.relay.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

RELAY_WORTHY_TYPES = {
    PacketType.TEXT,
    PacketType.POSITION,
    PacketType.TELEMETRY,
    PacketType.NODEINFO,
}

BROADCAST_ADDR_MESHTASTIC = "ffffffff"
BROADCAST_ADDR_MESHCORE = "ffff"


class RelayDecision:
    """Encapsulates the decision of whether to relay a packet."""

    def __init__(self, should_relay: bool, reason: str):
        self.should_relay = should_relay
        self.reason = reason


class RelayManager:
    """Smart relay engine that decides which packets to rebroadcast.

    Applies multiple filters to prevent flooding:
    - Deduplication: skip packets already seen
    - Rate limiting: enforce max TX per minute
    - Hop filtering: don't relay packets with 0 hops remaining
    - Type filtering: only relay useful packet types
    - Signal filtering: don't relay strong signals (nearby nodes)
    - Destination filtering: never relay unicast packets addressed to us

    The actual transmission is handled by an external radio
    (SX1262 via meshtastic-python serial interface).
    """

    def __init__(
        self,
        max_relay_per_minute: int = 20,
        burst_size: int = 5,
        min_relay_rssi: float = -110.0,
        max_relay_rssi: float = -50.0,
        enabled: bool = False,
    ):
        self._dedup = DeduplicationFilter()
        self._limiter = RateLimiter(max_relay_per_minute, burst_size)
        self._min_rssi = min_relay_rssi
        self._max_rssi = max_relay_rssi
        self._enabled = enabled
        self._local_node_hex: str | None = None
        self._relay_count = 0
        self._rejected_count = 0
        self._rejection_reasons: dict[str, int] = {}
        self._transmit_fn: Optional[callable] = None

    def set_local_node_id(self, node_hex: str) -> None:
        """Skip relay for unicast packets addressed to this Meshpoint."""
        self._local_node_hex = node_hex.lower()

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value
        logger.info("Relay %s", "enabled" if value else "disabled")

    def set_transmit_function(self, fn: callable) -> None:
        """Register the function used to transmit relay packets."""
        self._transmit_fn = fn

    def evaluate(self, packet: Packet) -> RelayDecision:
        """Decide whether a captured packet should be relayed."""
        if not self._enabled:
            return RelayDecision(False, "relay_disabled")

        if self._dedup.is_duplicate(packet.source_id, packet.packet_id):
            return RelayDecision(False, "duplicate")

        if packet.hop_limit <= 0:
            return RelayDecision(False, "no_hops_remaining")

        dest = (packet.destination_id or "").lower()
        if (
            self._local_node_hex
            and dest == self._local_node_hex
            and dest not in (BROADCAST_ADDR_MESHTASTIC, BROADCAST_ADDR_MESHCORE)
        ):
            return RelayDecision(False, "dest_local")

        if packet.packet_type not in RELAY_WORTHY_TYPES:
            return RelayDecision(False, "non_relayable_type")

        if packet.signal:
            if packet.signal.rssi > self._max_rssi:
                return RelayDecision(False, "signal_too_strong")
            if packet.signal.rssi < self._min_rssi:
                return RelayDecision(False, "signal_too_weak")

        if not self._limiter.allow():
            return RelayDecision(False, "rate_limited")

        return RelayDecision(True, "approved")

    async def process_packet(self, packet: Packet) -> None:
        """Evaluate and optionally relay a packet."""
        decision = self.evaluate(packet)

        if decision.should_relay:
            await self._relay(packet)
            self._relay_count += 1
        else:
            self._rejected_count += 1
            self._rejection_reasons[decision.reason] = (
                self._rejection_reasons.get(decision.reason, 0) + 1
            )
            logger.debug(
                "Relay rejected [%s]: %s from %s",
                decision.reason,
                packet.packet_id,
                packet.source_id,
            )

    async def _relay(self, packet: Packet) -> None:
        """Transmit a relay packet via the attached radio.

        The registered transmit function may be either synchronous
        (legacy USB-companion path that calls a blocking serial API)
        or asynchronous (native onboard SX1302 path that schedules
        through asyncio). We detect at call time and dispatch
        accordingly so both backends share the same RelayManager.
        """
        if self._transmit_fn is None:
            logger.warning("No transmit function registered for relay")
            return

        logger.info(
            "RELAY [%s] %s -> %s (type=%s, rssi=%.1f)",
            packet.protocol.value,
            packet.source_id,
            packet.destination_id,
            packet.packet_type.value,
            packet.signal.rssi if packet.signal else 0,
        )

        try:
            if asyncio.iscoroutinefunction(self._transmit_fn):
                await self._transmit_fn(packet)
            else:
                # Sync transmit (legacy USB-companion path) blocks on
                # serial I/O, so it must run off the event loop.
                await asyncio.to_thread(self._transmit_fn, packet)
        except Exception:
            logger.exception("Relay transmission failed")

    def get_stats(self) -> dict:
        return {
            "enabled": self._enabled,
            "relayed": self._relay_count,
            "rejected": self._rejected_count,
            "rejection_reasons": dict(self._rejection_reasons),
            "dedup_cache_size": self._dedup.size,
            "rate_remaining": self._limiter.remaining_capacity,
            "current_rate": self._limiter.current_rate,
        }
