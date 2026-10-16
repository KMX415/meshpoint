"""Periodic Meshtastic POSITION broadcaster."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Optional

from src.transmit.broadcast_interval import (
    BroadcastIntervalController,
    clamp_interval_minutes,
)
from src.transmit.tx_service import TxService

logger = logging.getLogger(__name__)


class PositionBroadcaster:
    """Schedules POSITION broadcasts when coordinates are available."""

    def __init__(
        self,
        tx_service: TxService,
        *,
        interval_minutes: int = 15,
        startup_delay_seconds: int = 180,
        coords_provider: Callable[[], tuple[float, float, float | None] | None],
    ):
        self._tx = tx_service
        self._coords_provider = coords_provider
        self._task: Optional[asyncio.Task] = None
        self._running = False
        interval_seconds = clamp_interval_minutes(
            interval_minutes,
            field_name="transmit.position.interval_minutes",
        ) * 60
        self._schedule = BroadcastIntervalController(
            startup_delay_seconds=startup_delay_seconds,
            interval_seconds=interval_seconds,
            field_name="transmit.position.interval_minutes",
        )

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    @property
    def interval_seconds(self) -> int:
        return self._schedule.interval_seconds

    @property
    def startup_delay_seconds(self) -> int:
        return self._schedule.startup_delay_seconds

    @property
    def last_sent_at(self) -> Optional[datetime]:
        return self._schedule.last_sent_at

    @property
    def next_due_at(self) -> Optional[datetime]:
        return self._schedule.next_due_at(running=self._running)

    def set_interval(self, minutes: int) -> int:
        return self._schedule.set_interval(minutes)

    async def start(self) -> None:
        if self.is_running:
            return
        self._running = True
        self._schedule.begin()
        self._task = asyncio.create_task(self._loop(), name="position-broadcaster")
        logger.info(
            "Position broadcaster scheduled: first TX in %ds, interval %ds",
            self._schedule.startup_delay_seconds,
            self._schedule.interval_seconds,
        )

    async def stop(self, timeout: float = 5.0) -> None:
        self._running = False
        task = self._task
        if task is None:
            return
        task.cancel()
        try:
            await asyncio.wait_for(task, timeout=timeout)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
        finally:
            self._task = None

    async def _loop(self) -> None:
        try:
            await self._schedule.run_loop(
                is_running=lambda: self._running,
                on_due=self._broadcast_once,
                loop_name="Position broadcaster",
            )
        except Exception:
            logger.exception("Position broadcaster loop crashed")

    async def _broadcast_once(self) -> None:
        # Hidden/unavailable coordinates must still advance the attempt schedule.
        self._schedule.mark_attempt()
        coords = self._coords_provider()
        if coords is None:
            logger.debug("Position broadcast skipped: no coordinates")
            return
        lat, lon, alt = coords
        result = await self._tx.send_position(lat, lon, alt)
        if result.success:
            self._schedule.mark_sent()
            logger.info(
                "Position broadcast OK: id=%s airtime=%dms",
                result.packet_id,
                result.airtime_ms,
            )
        else:
            logger.warning("Position broadcast skipped: %s", result.error)
