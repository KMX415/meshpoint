from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator

from src.capture.base import CaptureSource
from src.models.packet import RawCapture

logger = logging.getLogger(__name__)


class CaptureCoordinator:
    """Manages multiple capture sources and merges their output streams.

    Each source runs in its own async task. Captured packets are placed
    into a shared queue for the decode pipeline to consume.
    """

    def __init__(self, max_queue_size: int = 1000):
        self._sources: list[CaptureSource] = []
        self._tasks: list[asyncio.Task] = []
        self._queue: asyncio.Queue[RawCapture] = asyncio.Queue(
            maxsize=max_queue_size
        )
        self._running = False

    def add_source(self, source: CaptureSource) -> None:
        self._sources.append(source)
        logger.info("Added capture source: %s", source.name)

    async def start(self) -> None:
        self._running = True
        for source in self._sources:
            await source.start()
            task = asyncio.create_task(
                self._run_source(source),
                name=f"capture-{source.name}",
            )
            self._tasks.append(task)
        logger.info(
            "CaptureCoordinator started with %d sources", len(self._sources)
        )

    async def stop(self) -> None:
        self._running = False
        for source in self._sources:
            await source.stop()
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        logger.info("CaptureCoordinator stopped")

    def concentrator_rx_stats(self) -> dict[str, int]:
        """SX1302 CRC counters when a concentrator source is registered."""
        for source in self._sources:
            stats = getattr(source, "rx_crc_stats", None)
            if stats is not None:
                bad, no_crc = stats
                return {"crc_bad_total": bad, "no_crc_total": no_crc}
        return {"crc_bad_total": 0, "no_crc_total": 0}

    async def packets(self) -> AsyncIterator[RawCapture]:
        """Yield packets from all sources via the shared queue."""
        while self._running:
            try:
                raw = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0
                )
                yield raw
            except asyncio.TimeoutError:
                continue

    async def _run_source(self, source: CaptureSource) -> None:
        try:
            async for raw_capture in source.packets():
                if not self._running:
                    break
                try:
                    self._queue.put_nowait(raw_capture)
                except asyncio.QueueFull:
                    logger.warning(
                        "Capture queue full, dropping packet from %s",
                        source.name,
                    )
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception(
                "Capture source %s crashed", source.name
            )

    @property
    def source_count(self) -> int:
        return len(self._sources)

    @property
    def queue_size(self) -> int:
        return self._queue.qsize()
