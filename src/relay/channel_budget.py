"""Per-channel rolling ToA budget for relay TX only.

Tracks estimated airtime per Meshtastic channel index over a sliding
window and enforces operator throttle percentages. Does not affect
native concentrator TX (``transmit.enabled``).
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass

from src.analytics.toa_estimate import estimate_packet_toa_ms
from src.models.packet import Packet
from src.transmit.duty_cycle import DEFAULT_WINDOW_SECONDS, DUTY_CYCLE_LIMITS

_MAX_CHANNEL = 7


def resolve_relay_regulatory_ceiling(region: str) -> float | None:
    """Return regional duty ceiling when below 100%, else operator-only."""
    limit = DUTY_CYCLE_LIMITS.get(region, 1.0)
    if limit >= 100.0:
        return None
    return limit


def normalize_channel_throttle(
    throttle_percent: dict[str, float] | None,
) -> dict[str, float]:
    """Validate and normalize channel throttle map (keys 0–7, values 1–100)."""
    if not throttle_percent:
        return {}
    normalized: dict[str, float] = {}
    for key, value in throttle_percent.items():
        ch = str(key).strip()
        if not ch.isdigit() or int(ch) < 0 or int(ch) > _MAX_CHANNEL:
            raise ValueError(f"invalid channel throttle key: {key!r}")
        pct = float(value)
        if not 1.0 <= pct <= 100.0:
            raise ValueError(
                f"channel {ch} throttle must be between 1 and 100 percent"
            )
        normalized[ch] = pct
    return normalized


def throttle_percent_for(
    channel: int,
    throttle_percent: dict[str, float],
) -> float:
    """Configured throttle for *channel*; default 100% when omitted."""
    return float(throttle_percent.get(str(channel), 100.0))


def effective_limit_percent(
    channel: int,
    throttle_percent: dict[str, float],
    regulatory_ceiling: float | None,
) -> float:
    """Operator throttle capped by regional ceiling when present."""
    throttle = throttle_percent_for(channel, throttle_percent)
    if regulatory_ceiling is None:
        return throttle
    return min(throttle, regulatory_ceiling)


@dataclass
class _TxRecord:
    timestamp: float
    airtime_ms: int


class ChannelBudget:
    """Rolling per-channel relay airtime budget."""

    def __init__(
        self,
        *,
        throttle_percent: dict[str, float] | None = None,
        region: str = "US",
        window_seconds: int = DEFAULT_WINDOW_SECONDS,
        default_sf: int = 11,
        default_bw_khz: float = 250.0,
        default_preamble: int = 16,
    ):
        self._throttle = normalize_channel_throttle(throttle_percent)
        self._region = region
        self._regulatory_ceiling = resolve_relay_regulatory_ceiling(region)
        self._window_seconds = window_seconds
        self._default_sf = default_sf
        self._default_bw_khz = default_bw_khz
        self._default_preamble = default_preamble
        self._records: dict[int, deque[_TxRecord]] = defaultdict(deque)

    @property
    def region(self) -> str:
        return self._region

    @property
    def regulatory_ceiling_percent(self) -> float | None:
        return self._regulatory_ceiling

    @property
    def window_seconds(self) -> int:
        return self._window_seconds

    def reload(
        self,
        *,
        throttle_percent: dict[str, float] | None = None,
        region: str | None = None,
    ) -> None:
        if throttle_percent is not None:
            self._throttle = normalize_channel_throttle(throttle_percent)
        if region is not None:
            self._region = region
            self._regulatory_ceiling = resolve_relay_regulatory_ceiling(region)

    def estimate_packet_toa_ms(self, packet: Packet) -> int:
        return estimate_packet_toa_ms(
            packet,
            default_sf=self._default_sf,
            default_bw_khz=self._default_bw_khz,
            default_preamble=self._default_preamble,
        )

    def _channel_index(self, packet: Packet) -> int:
        ch = int(packet.channel_hash or 0)
        return max(0, min(_MAX_CHANNEL, ch))

    def check_packet(self, packet: Packet) -> bool:
        channel = self._channel_index(packet)
        return self.check_budget(channel, self.estimate_packet_toa_ms(packet))

    def check_budget(self, channel: int, airtime_ms: int) -> bool:
        channel = max(0, min(_MAX_CHANNEL, int(channel)))
        self._prune(channel)
        limit_pct = effective_limit_percent(
            channel, self._throttle, self._regulatory_ceiling
        )
        window_ms = self._window_seconds * 1000
        current_ms = sum(r.airtime_ms for r in self._records[channel])
        projected = ((current_ms + airtime_ms) / window_ms) * 100
        return projected <= limit_pct

    def record_packet(self, packet: Packet) -> None:
        channel = self._channel_index(packet)
        self.record_tx(channel, self.estimate_packet_toa_ms(packet))

    def record_tx(self, channel: int, airtime_ms: int) -> None:
        channel = max(0, min(_MAX_CHANNEL, int(channel)))
        self._records[channel].append(
            _TxRecord(timestamp=time.monotonic(), airtime_ms=airtime_ms)
        )
        self._prune(channel)

    def channel_status(self, channel: int) -> dict:
        channel = max(0, min(_MAX_CHANNEL, int(channel)))
        self._prune(channel)
        throttle = throttle_percent_for(channel, self._throttle)
        limit_pct = effective_limit_percent(
            channel, self._throttle, self._regulatory_ceiling
        )
        used_ms = sum(r.airtime_ms for r in self._records[channel])
        window_ms = self._window_seconds * 1000
        budget_ms = int(window_ms * limit_pct / 100)
        usage_pct = round((used_ms / window_ms) * 100, 2) if window_ms else 0.0
        return {
            "channel": channel,
            "throttle_percent": throttle,
            "effective_limit_percent": limit_pct,
            "usage_percent": usage_pct,
            "used_toa_ms_estimated": used_ms,
            "budget_toa_ms_estimated": budget_ms,
            "remaining_toa_ms_estimated": max(0, budget_ms - used_ms),
        }

    def all_channel_status(self) -> list[dict]:
        return [self.channel_status(ch) for ch in range(_MAX_CHANNEL + 1)]

    def summary(self) -> dict:
        channels = self.all_channel_status()
        total_used = sum(c["used_toa_ms_estimated"] for c in channels)
        total_budget = sum(c["budget_toa_ms_estimated"] for c in channels)
        window_ms = self._window_seconds * 1000
        aggregate_usage = (
            round((total_used / window_ms) * 100, 2) if window_ms else 0.0
        )
        return {
            "region": self._region,
            "regulatory_ceiling_percent": self._regulatory_ceiling,
            "window_seconds": self._window_seconds,
            "estimate_note": (
                "ToA estimates — not spectrum analyser measurements"
            ),
            "relay_total_usage_percent": aggregate_usage,
            "channels": channels,
        }

    def _prune(self, channel: int) -> None:
        cutoff = time.monotonic() - self._window_seconds
        records = self._records[channel]
        while records and records[0].timestamp < cutoff:
            records.popleft()


def build_channel_budget(
    *,
    throttle_percent: dict[str, float] | None,
    region: str,
    default_sf: int,
    default_bw_khz: float,
    default_preamble: int = 16,
) -> ChannelBudget:
    return ChannelBudget(
        throttle_percent=throttle_percent,
        region=region,
        default_sf=default_sf,
        default_bw_khz=default_bw_khz,
        default_preamble=default_preamble,
    )
