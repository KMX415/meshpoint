"""Shared interval scheduling for periodic Meshtastic mesh broadcasts."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

INTERVAL_DISABLED = 0
INTERVAL_MIN_MINUTES = 5
INTERVAL_MAX_MINUTES = 1440


def clamp_interval_minutes(
    value: int,
    *,
    field_name: str = "transmit.interval_minutes",
) -> int:
    """Clamp interval minutes; ``0`` disables periodic broadcasts."""
    if value == INTERVAL_DISABLED:
        return INTERVAL_DISABLED
    if value < 0:
        logger.warning(
            "%s=%d is negative, treating as disabled (0).",
            field_name,
            value,
        )
        return INTERVAL_DISABLED
    if value < INTERVAL_MIN_MINUTES:
        logger.warning(
            "%s=%d is below minimum %d, clamping. "
            "Set to 0 to disable broadcasts entirely.",
            field_name,
            value,
            INTERVAL_MIN_MINUTES,
        )
        return INTERVAL_MIN_MINUTES
    if value > INTERVAL_MAX_MINUTES:
        logger.warning(
            "%s=%d is above maximum %d, clamping.",
            field_name,
            value,
            INTERVAL_MAX_MINUTES,
        )
        return INTERVAL_MAX_MINUTES
    return value


class BroadcastIntervalController:
    """Hot-reload interval state shared by NodeInfo, position, and telemetry."""

    def __init__(
        self,
        *,
        startup_delay_seconds: int,
        interval_seconds: int,
        field_name: str = "transmit.interval_minutes",
    ):
        self._field_name = field_name
        self._startup_delay = max(0, startup_delay_seconds)
        self._interval = interval_seconds
        self._interval_changed = asyncio.Event()
        self._started_at: Optional[datetime] = None
        self._last_sent_at: Optional[datetime] = None
        self._last_attempt_at: Optional[datetime] = None

    @property
    def interval_seconds(self) -> int:
        return self._interval

    @property
    def startup_delay_seconds(self) -> int:
        return self._startup_delay

    @property
    def last_sent_at(self) -> Optional[datetime]:
        return self._last_sent_at

    def mark_sent(self) -> None:
        self._last_sent_at = datetime.now(timezone.utc)

    def mark_attempt(self) -> None:
        """Defer the next attempt without claiming a successful transmission."""
        self._last_attempt_at = datetime.now(timezone.utc)

    def _schedule_anchor(self) -> Optional[datetime]:
        times = [t for t in (self._last_sent_at, self._last_attempt_at) if t is not None]
        return max(times) if times else None

    def begin(self) -> None:
        self._started_at = datetime.now(timezone.utc)

    def next_due_at(self, *, running: bool) -> Optional[datetime]:
        if not running:
            return None
        if self._interval == 0:
            return None
        anchor = self._schedule_anchor()
        if anchor is not None:
            return anchor + timedelta(seconds=self._interval)
        if self._started_at is not None:
            return self._started_at + timedelta(seconds=self._startup_delay)
        return None

    def set_interval(self, minutes: int) -> int:
        clamped = clamp_interval_minutes(minutes, field_name=self._field_name)
        previous = self._interval
        self._interval = clamped * 60
        if previous != self._interval:
            logger.info(
                "%s interval hot-reloaded: %ds -> %ds",
                self._field_name,
                previous,
                self._interval,
            )
        if (
            self._interval > 0
            and self._last_sent_at is None
            and self._started_at is not None
        ):
            self._started_at = (
                datetime.now(timezone.utc)
                - timedelta(seconds=self._startup_delay)
            )
        self._interval_changed.set()
        return clamped

    async def run_loop(
        self,
        *,
        is_running: Callable[[], bool],
        on_due: Callable[[], Awaitable[None]],
        loop_name: str,
    ) -> None:
        try:
            if self._startup_delay > 0:
                self._interval_changed.clear()
                try:
                    await asyncio.wait_for(
                        self._interval_changed.wait(),
                        timeout=self._startup_delay,
                    )
                except asyncio.TimeoutError:
                    pass
            while is_running():
                if self._interval == 0:
                    self._interval_changed.clear()
                    await self._interval_changed.wait()
                    continue

                if self._is_due_now():
                    await on_due()
                    if not is_running():
                        break

                self._interval_changed.clear()
                sleep_seconds = self._sleep_until_next()
                if sleep_seconds <= 0:
                    continue
                try:
                    await asyncio.wait_for(
                        self._interval_changed.wait(),
                        timeout=sleep_seconds,
                    )
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            logger.debug("%s cancelled", loop_name)
            raise

    def _is_due_now(self) -> bool:
        if self._interval == 0:
            return False
        anchor = self._schedule_anchor()
        if anchor is None:
            return True
        next_due = anchor + timedelta(seconds=self._interval)
        return datetime.now(timezone.utc) >= next_due

    def _sleep_until_next(self) -> float:
        if self._interval == 0:
            return 0.0
        anchor = self._schedule_anchor()
        if anchor is None:
            return float(self._interval)
        next_due = anchor + timedelta(seconds=self._interval)
        remaining = (next_due - datetime.now(timezone.utc)).total_seconds()
        return max(0.0, remaining)
