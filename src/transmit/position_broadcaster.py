"""Periodic Meshtastic POSITION broadcaster."""

from __future__ import annotations

import logging
from typing import Callable, Optional

from src.transmit.nodeinfo_broadcaster import clamp_interval_minutes
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
        self._interval = clamp_interval_minutes(interval_minutes) * 60
        self._startup_delay = max(0, startup_delay_seconds)
        self._coords_provider = coords_provider
        self._task: Optional[object] = None
        self._running = False

    async def start(self) -> None:
        if self._interval == 0 or self._running:
            return
        import asyncio

        self._running = True
        self._task = asyncio.create_task(self._loop(), name="position-broadcaster")
        logger.info(
            "Position broadcaster scheduled: first TX in %ds, interval %ds",
            self._startup_delay,
            self._interval,
        )

    async def stop(self, timeout: float = 5.0) -> None:
        import asyncio

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
        import asyncio

        try:
            if self._startup_delay > 0:
                await asyncio.sleep(self._startup_delay)
            while self._running:
                coords = self._coords_provider()
                if coords is None:
                    logger.debug("Position broadcast skipped: no coordinates")
                else:
                    lat, lon, alt = coords
                    result = await self._tx.send_position(lat, lon, alt)
                    if not result.success:
                        logger.warning("Position broadcast skipped: %s", result.error)
                if self._interval <= 0:
                    break
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Position broadcaster loop crashed")
