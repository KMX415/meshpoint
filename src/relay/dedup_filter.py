from __future__ import annotations

import logging
import time
from collections import OrderedDict

logger = logging.getLogger(__name__)


class DeduplicationFilter:
    """Tracks recently seen packet IDs to prevent relay loops.

    Uses an LRU cache with TTL expiration. A packet is considered
    a duplicate if its (source_id, packet_id) pair was seen within
    the TTL window.
    """

    def __init__(
        self,
        max_entries: int = 10_000,
        ttl_seconds: float = 300.0,
    ):
        self._max_entries = max_entries
        self._ttl = ttl_seconds
        self._seen: OrderedDict[str, float] = OrderedDict()

    def is_duplicate(self, source_id: str, packet_id: str) -> bool:
        """Check if this packet was recently seen. If not, record it."""
        key = f"{source_id}:{packet_id}"
        now = time.monotonic()

        self._evict_expired(now)

        if key in self._seen:
            return True

        self._seen[key] = now
        self._enforce_max_size()
        return False

    def _evict_expired(self, now: float) -> None:
        cutoff = now - self._ttl
        while self._seen:
            oldest_key, oldest_time = next(iter(self._seen.items()))
            if oldest_time > cutoff:
                break
            self._seen.popitem(last=False)

    def _enforce_max_size(self) -> None:
        while len(self._seen) > self._max_entries:
            self._seen.popitem(last=False)

    @property
    def size(self) -> int:
        return len(self._seen)

    def clear(self) -> None:
        self._seen.clear()
