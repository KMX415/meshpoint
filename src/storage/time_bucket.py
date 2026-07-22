"""Shared time-bucketing helper for downsampled history queries.

Used by TelemetryRepository.get_history() and
PacketRepository.get_signal_history() so a long-lived node's chart data
stays bounded to roughly ``limit`` points instead of a plain LIMIT
silently dropping the newest rows.

Credit: javastraat/meshpoint ``b10610a``.
"""

from __future__ import annotations

from datetime import datetime


def bucket_seconds(span_row: dict | None, limit: int, hours: float) -> int:
    """Bucket width in seconds for a downsampled history query.

    Derived from the actual span of matching data (``lo``/``hi``) rather
    than the requested ``hours`` window, so over-sized request windows
    do not crush a short real history into coarse buckets. Floored at
    60 seconds.
    """
    limit = max(limit, 1)
    lo = span_row.get("lo") if span_row else None
    hi = span_row.get("hi") if span_row else None
    if lo and hi:
        span = (
            datetime.fromisoformat(hi) - datetime.fromisoformat(lo)
        ).total_seconds()
        if span > 0:
            return max(60, int(span / limit))
    return max(60, int((hours * 3600) / limit))
