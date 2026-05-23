"""Public radar feed for the auth pages.

The unauthenticated ``/login`` and ``/setup`` pages render a radar
that pulses each time the local node hears a packet. To keep the
illusion honest without leaking sensitive data to anonymous LAN
clients, this endpoint returns a deliberately scrubbed slice of the
recent receive history: just the rate, RSSI bucket, and a
randomized bearing/distance pair derived from the packet's signal
strength.

Specifically excluded -- these never appear in the response:

* node ids (source / destination)
* GPS coordinates
* channel hashes
* hardware fingerprints
* packet payloads

The rate-limit (one request per IP every 4 seconds) is enforced in
memory, so a hostile LAN client cannot turn this into a stream of
metadata about who is on the air.
"""

from __future__ import annotations

import random
import time
from collections import deque
from dataclasses import asdict, dataclass
from typing import Iterable

from fastapi import APIRouter, HTTPException, Request, status

router = APIRouter(prefix="/api/public", tags=["public"])

_recent: deque = deque(maxlen=64)
_rate_limit: dict[str, float] = {}
_RATE_LIMIT_SECONDS = 4.0


@dataclass(frozen=True)
class PublicBlip:
    """One scrubbed packet sample for radar rendering.

    ``bearing`` is in degrees (0--359), ``distance`` is normalized to
    [0, 1] where 1 is the outer ring. Both are derived from RSSI
    plus a small amount of randomness so the visual is informative
    but never identifies a specific node.
    """

    timestamp: float
    rssi_bucket: str
    bearing: int
    distance: float

    def to_dict(self) -> dict:
        return asdict(self)


def record_packet(rssi: float | None) -> None:
    """Hook the live pipeline so each receive seeds a public blip.

    Called from the dashboard's packet callback. The scrubber here
    must never see a node id; we deliberately accept only the
    minimum field set the UI needs.
    """
    bucket = _rssi_bucket(rssi)
    bearing = random.randint(0, 359)
    distance = _distance_from_rssi(rssi)
    _recent.append(PublicBlip(
        timestamp=time.time(),
        rssi_bucket=bucket,
        bearing=bearing,
        distance=distance,
    ))


def reset_state() -> None:
    """Test helper: clear the in-memory feed + rate-limit table."""
    _recent.clear()
    _rate_limit.clear()


def _rssi_bucket(rssi: float | None) -> str:
    if rssi is None:
        return "unknown"
    if rssi >= -70:
        return "strong"
    if rssi >= -90:
        return "medium"
    return "weak"


def _distance_from_rssi(rssi: float | None) -> float:
    if rssi is None:
        return 0.6 + random.random() * 0.3
    clamped = max(-130.0, min(-50.0, float(rssi)))
    normalized = (clamped + 130.0) / 80.0
    inverted = 1.0 - normalized
    jitter = random.uniform(-0.05, 0.05)
    return max(0.05, min(0.98, inverted + jitter))


def _client_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


@router.get("/recent_rx")
async def recent_rx(request: Request) -> dict:
    ip = _client_ip(request)
    now = time.time()
    last = _rate_limit.get(ip, 0.0)
    if now - last < _RATE_LIMIT_SECONDS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="rate_limited",
            headers={"Retry-After": str(int(_RATE_LIMIT_SECONDS))},
        )
    _rate_limit[ip] = now
    cutoff = now - 60.0
    blips = [b.to_dict() for b in _recent if b.timestamp >= cutoff]
    return {"blips": blips, "count": len(blips), "window_seconds": 60}


def public_radar_packet_callback(packet) -> None:
    """Seed a blip from a live packet.

    Wraps :func:`record_packet` so callers can register the function
    directly with ``coord.on_packet`` without depending on the
    module-private name. Defensive about the packet's signal block.
    """
    rssi = None
    try:
        rssi = packet.signal.rssi if packet.signal else None
    except AttributeError:
        rssi = None
    record_packet(rssi)


def public_radar_iter() -> Iterable[dict]:
    """Iterator over the live blip ring (debug only)."""
    return [b.to_dict() for b in _recent]


__all__ = [
    "PublicBlip",
    "router",
    "record_packet",
    "reset_state",
    "public_radar_packet_callback",
    "public_radar_iter",
]
