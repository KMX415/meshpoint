"""In-memory collector for telemetry received from other nodes.

Every inbound LXMF message carrying a ``FIELD_TELEMETRY`` frame is decoded
(``telemetry.decode_telemetry``) and recorded here, keyed by the sender's
destination hash -- latest reading only, no history. Backs
``GET /api/reticulum/telemetry/peers`` and the Reticulum page's Telemetry
tab / map.

Deliberately in-memory (like the announce ring buffer): it starts empty
on restart and rebuilds as peers report. A stale entry is dropped after
``_MAX_AGE_S`` so the map doesn't show nodes that went quiet hours ago.

FastAPI-free; stdlib only.
"""

from __future__ import annotations

import time

_MAX_AGE_S = 24 * 3600      # drop a peer we haven't heard telemetry from in a day
_MAX_PEERS = 500            # hard cap (public network safety, same spirit as the peer roster)


class TelemetryStore:
    def __init__(self):
        self._by_hash: dict[str, dict] = {}

    def record(self, destination_hash: str, decoded: dict, name: str = "") -> None:
        """Store one decoded telemetry reading. ``decoded`` is
        ``telemetry.decode_telemetry()``'s output. A frame with nothing
        useful in it (no temp / info / location) is ignored."""
        if not destination_hash or not isinstance(decoded, dict):
            return
        if not any(k in decoded for k in ("temperature_c", "info", "latitude")):
            return
        self._by_hash[destination_hash] = {
            "destination_hash": destination_hash,
            "name": name or self._by_hash.get(destination_hash, {}).get("name", ""),
            "received_at": time.time(),
            **decoded,
        }
        self._prune()

    def _prune(self) -> None:
        cutoff = time.time() - _MAX_AGE_S
        stale = [h for h, e in self._by_hash.items() if e["received_at"] < cutoff]
        for h in stale:
            del self._by_hash[h]
        if len(self._by_hash) > _MAX_PEERS:
            # keep the most recently heard
            keep = sorted(
                self._by_hash.items(), key=lambda kv: kv[1]["received_at"], reverse=True,
            )[:_MAX_PEERS]
            self._by_hash = dict(keep)

    def all(self) -> list[dict]:
        """Every current reading, newest first."""
        self._prune()
        return sorted(
            self._by_hash.values(), key=lambda e: e["received_at"], reverse=True,
        )

    def count(self) -> int:
        return len(self._by_hash)
