"""Per-key failed-login lockout tracker.

Single responsibility: keep an in-memory tally of failed login
attempts keyed by a caller-supplied identifier (typically the
attempted username, or a remote-IP fallback for anonymous probes)
and answer two questions:

- "Is this key currently locked?" -> ``remaining_seconds()``
- "Record a failure / success" -> ``register_failure``, ``register_success``

Storage is a plain dict guarded by ``threading.Lock``, so the tracker
is safe to share across the FastAPI worker threadpool. There is no
persistence: a process restart resets all counters by design (the
attacker would have already triggered a config-rotation alarm by
then).

The clock is injected (``clock=time.monotonic`` by default) so unit
tests can advance time without sleeping.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional

_DEFAULT_MAX_ATTEMPTS = 5
_DEFAULT_COOLDOWN_MINUTES = 5


@dataclass
class _AttemptState:
    failures: int = 0
    locked_until: float = 0.0


class LockoutTracker:
    """Throttle repeated failed logins per key with a fixed cooldown."""

    def __init__(
        self,
        max_attempts: int = _DEFAULT_MAX_ATTEMPTS,
        cooldown_minutes: int = _DEFAULT_COOLDOWN_MINUTES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if cooldown_minutes < 1:
            raise ValueError("cooldown_minutes must be >= 1")
        self._max_attempts = max_attempts
        self._cooldown_seconds = cooldown_minutes * 60
        self._clock = clock
        self._states: dict[str, _AttemptState] = {}
        self._lock = threading.Lock()

    @property
    def max_attempts(self) -> int:
        return self._max_attempts

    def remaining_seconds(self, key: str) -> Optional[int]:
        """Return seconds until ``key`` unlocks, or ``None`` if not locked."""
        if not key:
            return None
        with self._lock:
            state = self._states.get(key)
            if state is None or state.locked_until == 0.0:
                return None
            now = self._clock()
            if now >= state.locked_until:
                self._states.pop(key, None)
                return None
            return int(state.locked_until - now) + 1

    def register_failure(self, key: str) -> Optional[int]:
        """Record a failed attempt for ``key``.

        Returns the cooldown in seconds if the failure crossed the
        threshold, or ``None`` while the caller still has tries left.
        """
        if not key:
            return None
        with self._lock:
            state = self._states.setdefault(key, _AttemptState())
            now = self._clock()
            if state.locked_until > now:
                return int(state.locked_until - now) + 1
            state.failures += 1
            if state.failures >= self._max_attempts:
                state.locked_until = now + self._cooldown_seconds
                return self._cooldown_seconds
            return None

    def register_success(self, key: str) -> None:
        """Clear all state for ``key`` after a successful login."""
        if not key:
            return
        with self._lock:
            self._states.pop(key, None)
