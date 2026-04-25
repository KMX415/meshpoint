"""Async spectral sweep service.

Steps through a frequency range, fires one SX1261 spectral scan per step,
and broadcasts each result row over the WebSocket as a 'spectral_row' event:

    {"type": "spectral_row", "data": {"freq_hz": int, "rssi_dbm": int, "ts": float}}

SX1261 access is serialized with TX operations via a shared asyncio.Lock.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from src.spectral import scan_bindings as _hal

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 0.005   # seconds between status polls
_SCAN_TIMEOUT  = 3.0     # seconds before we abort a stuck scan
_STEP_PAUSE    = 0.01    # seconds between frequency steps


@dataclass
class SweepConfig:
    freq_start_hz: int
    freq_stop_hz: int
    freq_step_hz: int = 200_000    # 200 kHz steps
    nb_scan: int = 2000            # HAL accumulation count


@dataclass
class ScanStatus:
    running: bool = False
    freq_start_hz: int = 0
    freq_stop_hz: int = 0
    freq_step_hz: int = 200_000
    nb_scan: int = 2000
    available: bool = field(default_factory=_hal.is_available)


class ScanService:
    def __init__(self, ws_manager=None, sx1261_lock: asyncio.Lock | None = None):
        self._ws = ws_manager
        self._lock = sx1261_lock or asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._cfg: SweepConfig | None = None

    @property
    def status(self) -> ScanStatus:
        cfg = self._cfg
        return ScanStatus(
            running=self._task is not None and not self._task.done(),
            freq_start_hz=cfg.freq_start_hz if cfg else 0,
            freq_stop_hz=cfg.freq_stop_hz if cfg else 0,
            freq_step_hz=cfg.freq_step_hz if cfg else 200_000,
            nb_scan=cfg.nb_scan if cfg else 2000,
        )

    def start(self, cfg: SweepConfig) -> bool:
        if self._task and not self._task.done():
            return False
        if not _hal.is_available():
            logger.warning("Spectral scan requested but libloragw unavailable")
            return False
        self._cfg = cfg
        self._task = asyncio.get_running_loop().create_task(self._sweep(cfg))
        logger.info(
            "Spectral sweep started: %d–%d Hz, step=%d Hz",
            cfg.freq_start_hz, cfg.freq_stop_hz, cfg.freq_step_hz,
        )
        return True

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            logger.info("Spectral sweep stop requested")

    async def _sweep(self, cfg: SweepConfig) -> None:
        try:
            freq = cfg.freq_start_hz
            while freq <= cfg.freq_stop_hz:
                rssi = await self._single_scan(freq, cfg.nb_scan)
                if rssi is not None:
                    await self._broadcast(freq, rssi)
                freq += cfg.freq_step_hz
                await asyncio.sleep(_STEP_PAUSE)
        except asyncio.CancelledError:
            async with self._lock:
                await asyncio.to_thread(_hal.scan_abort)
            logger.info("Spectral sweep cancelled")
        except Exception:
            logger.exception("Spectral sweep error")

    async def _single_scan(self, freq_hz: int, nb_scan: int) -> int | None:
        async with self._lock:
            ok = await asyncio.to_thread(_hal.scan_start, freq_hz, nb_scan)
            if not ok:
                return None

            deadline = time.monotonic() + _SCAN_TIMEOUT
            while time.monotonic() < deadline:
                await asyncio.sleep(_POLL_INTERVAL)
                status = await asyncio.to_thread(_hal.scan_get_status)
                if status == _hal.STATUS_COMPLETED:
                    levels, counts = await asyncio.to_thread(_hal.scan_get_results)
                    return _hal.peak_rssi(levels, counts)
                if status == _hal.STATUS_ABORTED:
                    return None

            await asyncio.to_thread(_hal.scan_abort)
            return None

    async def _broadcast(self, freq_hz: int, rssi_dbm: int) -> None:
        if self._ws is None:
            return
        try:
            await self._ws.broadcast("spectral_row", {
                "freq_hz": freq_hz,
                "rssi_dbm": rssi_dbm,
                "ts": time.time(),
            })
        except Exception:
            pass
