"""Request-independent host CPU sampling shared by local and remote metrics."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class CpuSampler:
    """Cache CPU utilization over the preceding sampling interval (normally 2s).

    All counter reads occur on the service event-loop thread. Requests only
    read the cache and never reset psutil's thread-local measurement baseline.
    None means warming up or unavailable, not an idle CPU.
    """

    def __init__(self, interval: float = 2.0):
        self.interval = interval
        self.value: float | None = None

    async def _sample(self):
        try:
            import psutil
        except ImportError:
            logger.warning("CPU sampling unavailable: psutil not installed")
            return
        primed = False
        while True:
            try:
                value = psutil.cpu_percent(interval=None)
                if primed:
                    self.value = value
                primed = True
            except Exception:
                logger.exception("CPU sampling failed")
                self.value = None
                primed = False
            await asyncio.sleep(self.interval)

    @asynccontextmanager
    async def running(self):
        self.value = None
        task = asyncio.create_task(self._sample(), name="host-cpu-sampler")
        try:
            yield
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            self.value = None


cpu_sampler = CpuSampler()
