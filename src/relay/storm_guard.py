"""Memory-only storm/replay quarantine for relay (PR 12).

Detects abusive TX patterns (identical packet_id bursts or high packet
rate from one node) and temporarily blocks relay for that source. Separate
from the permanent YAML blocklist (PR 13).
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

from src.config import StormGuardConfig
from src.models.packet import Packet
from src.relay.node_id import normalize_node_id

logger = logging.getLogger(__name__)


@dataclass
class QuarantineEntry:
    node_id: str
    reason: str
    started_at_mono: float
    release_at_mono: float
    started_at: str
    trigger_packet_id: str | None = None

    def seconds_remaining(self, now: float) -> int:
        return max(0, int(self.release_at_mono - now))

    def to_dict(self, now: float | None = None) -> dict:
        ref = now if now is not None else time.monotonic()
        return {
            "node_id": self.node_id,
            "reason": self.reason,
            "started_at": self.started_at,
            "seconds_remaining": self.seconds_remaining(ref),
            "trigger_packet_id": self.trigger_packet_id,
        }


class StormGuard:
    """Rolling-window detector with in-memory quarantine state."""

    def __init__(
        self,
        config: StormGuardConfig,
        *,
        on_quarantine: Callable[[QuarantineEntry], None] | None = None,
        now_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._on_quarantine = on_quarantine
        self._now = now_fn
        self._packet_id_hits: dict[str, deque[tuple[float, str]]] = defaultdict(deque)
        self._rate_events: dict[str, deque[float]] = defaultdict(deque)
        self._active: dict[str, QuarantineEntry] = {}

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    def set_on_quarantine(
        self, callback: Callable[[QuarantineEntry], None] | None
    ) -> None:
        self._on_quarantine = callback

    def observe(self, packet: Packet) -> QuarantineEntry | None:
        """Track a decoded packet; quarantine on threshold breach."""
        if not self._config.enabled:
            return None

        node_id = normalize_node_id(packet.source_id)
        if not node_id:
            return None

        now = self._now()
        self._prune_expired(now)

        if node_id in self._active:
            return None

        reason = self._check_thresholds(node_id, packet.packet_id, now)
        if reason is None:
            return None

        entry = QuarantineEntry(
            node_id=node_id,
            reason=reason,
            started_at_mono=now,
            release_at_mono=now + float(self._config.quarantine_duration_seconds),
            started_at=datetime.now(timezone.utc).isoformat(),
            trigger_packet_id=packet.packet_id,
        )
        self._active[node_id] = entry
        logger.warning(
            "Storm guard quarantined %s (%s, packet_id=%s)",
            node_id,
            reason,
            packet.packet_id,
        )
        if self._on_quarantine:
            try:
                self._on_quarantine(entry)
            except Exception:
                logger.exception("Storm guard on_quarantine callback failed")
        return entry

    def is_quarantined(self, node_id: str) -> bool:
        if not self._config.enabled:
            return False
        now = self._now()
        self._prune_expired(now)
        return normalize_node_id(node_id) in self._active

    def release(self, node_id: str) -> bool:
        key = normalize_node_id(node_id)
        if key not in self._active:
            return False
        del self._active[key]
        self._packet_id_hits.pop(key, None)
        self._rate_events.pop(key, None)
        logger.info("Storm guard released %s (operator)", key)
        return True

    def snapshot(self) -> list[dict]:
        now = self._now()
        self._prune_expired(now)
        return [entry.to_dict(now) for entry in self._active.values()]

    def get_entry(self, node_id: str) -> QuarantineEntry | None:
        now = self._now()
        self._prune_expired(now)
        return self._active.get(normalize_node_id(node_id))

    def _check_thresholds(
        self, node_id: str, packet_id: str, now: float
    ) -> str | None:
        window = float(self._config.window_seconds)
        if window <= 0:
            return None

        rate_events = self._rate_events[node_id]
        rate_events.append(now)
        self._prune_deque(rate_events, now, window)
        if len(rate_events) >= self._config.rate_threshold_per_minute:
            return "rate_storm"

        if packet_id:
            hits = self._packet_id_hits[node_id]
            hits.append((now, packet_id))
            self._prune_hit_deque(hits, now, window)
            same_id = sum(1 for _ts, pid in hits if pid == packet_id)
            if same_id >= self._config.identical_packet_threshold:
                return "identical_packet_storm"

        return None

    def _prune_expired(self, now: float) -> None:
        expired = [
            node_id
            for node_id, entry in self._active.items()
            if now >= entry.release_at_mono
        ]
        for node_id in expired:
            del self._active[node_id]
            logger.info("Storm guard auto-released %s", node_id)

    @staticmethod
    def _prune_deque(events: deque[float], now: float, window: float) -> None:
        cutoff = now - window
        while events and events[0] < cutoff:
            events.popleft()

    @staticmethod
    def _prune_hit_deque(
        hits: deque[tuple[float, str]], now: float, window: float
    ) -> None:
        cutoff = now - window
        while hits and hits[0][0] < cutoff:
            hits.popleft()
