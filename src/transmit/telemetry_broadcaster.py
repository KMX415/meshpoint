"""Periodic Meshtastic device_metrics telemetry broadcaster."""

from __future__ import annotations

import logging
import time
from typing import Callable, Optional

from src.transmit.nodeinfo_broadcaster import clamp_interval_minutes
from src.transmit.tx_service import TxService

logger = logging.getLogger(__name__)


class TelemetryBroadcaster:
    """Schedules periodic TELEMETRY broadcasts via :class:`TxService`."""

    def __init__(
        self,
        tx_service: TxService,
        *,
        interval_minutes: int = 30,
        startup_delay_seconds: int = 120,
        metrics_provider: Callable[[], dict] | None = None,
    ):
        self._tx = tx_service
        self._interval = clamp_interval_minutes(interval_minutes) * 60
        self._startup_delay = max(0, startup_delay_seconds)
        self._metrics_provider = metrics_provider or (lambda: {})
        self._started_at = time.monotonic()
        self._task: Optional[object] = None
        self._running = False

    async def start(self) -> None:
        if self._interval == 0 or self._running:
            return
        import asyncio

        self._running = True
        self._task = asyncio.create_task(self._loop(), name="telemetry-broadcaster")
        logger.info(
            "Telemetry broadcaster scheduled: first TX in %ds, interval %ds",
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
                metrics = self._metrics_provider()
                uptime = int(time.monotonic() - self._started_at)
                result = await self._tx.send_telemetry(
                    battery_level=int(metrics.get("battery_level", 101)),
                    voltage=float(metrics.get("voltage", 5.0)),
                    channel_utilization=float(
                        metrics.get("channel_utilization", 0.0)
                    ),
                    air_util_tx=float(metrics.get("air_util_tx", 0.0)),
                    uptime_seconds=int(metrics.get("uptime_seconds", uptime)),
                )
                if not result.success:
                    logger.warning("Telemetry broadcast skipped: %s", result.error)
                if self._interval <= 0:
                    break
                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Telemetry broadcaster loop crashed")
