from __future__ import annotations

import logging
import time
from collections import deque

logger = logging.getLogger(__name__)


class RateLimiter:
    """Token-bucket rate limiter for relay transmissions.

    Prevents the relay from flooding the mesh by enforcing a maximum
    number of transmissions within a sliding time window.
    """

    def __init__(
        self,
        max_per_minute: int = 20,
        burst_size: int = 5,
    ):
        self._max_per_minute = max_per_minute
        self._burst_size = burst_size
        self._timestamps: deque[float] = deque()
        self._window_seconds = 60.0

    def allow(self) -> bool:
        """Check if a transmission is allowed under current rate limits."""
        now = time.monotonic()
        self._prune(now)

        if len(self._timestamps) >= self._max_per_minute:
            return False

        recent_count = sum(
            1 for t in self._timestamps if now - t < 5.0
        )
        if recent_count >= self._burst_size:
            return False

        self._timestamps.append(now)
        return True

    def _prune(self, now: float) -> None:
        cutoff = now - self._window_seconds
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()

    @property
    def current_rate(self) -> float:
        """Transmissions in the last minute."""
        now = time.monotonic()
        self._prune(now)
        return float(len(self._timestamps))

    @property
    def remaining_capacity(self) -> int:
        now = time.monotonic()
        self._prune(now)
        return max(0, self._max_per_minute - len(self._timestamps))
