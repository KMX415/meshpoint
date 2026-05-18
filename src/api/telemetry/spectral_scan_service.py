"""Background spectral-scan scheduler.

Runs one ``lgw_spectral_scan`` every ``interval_seconds`` and feeds
the result into the shared ``NoiseFloorTracker``. The scan itself
runs synchronously inside the loraconcentrator HAL; we offload it to
a thread (``asyncio.to_thread``) so the FastAPI event loop is not
blocked for the ~50 ms scan window.

Design choices:
    - One scan at a time. The loop awaits the result before the
      next sleep starts, so we never queue scans against a slow
      HAL.
    - Scans are skipped silently if the wrapper reports the
      concentrator is not started or if spectral scan is not
      supported. The packet-derived fallback in NoiseFloorTracker
      keeps the UI populated.
    - First scan is delayed by ``startup_delay_seconds`` to let the
      radio settle after ``lgw_start``.

Caller wires this from the FastAPI lifespan:

    service = SpectralScanService(
        wrapper=wrapper,
        tracker=tracker,
        frequency_hz=int(radio.frequency_mhz * 1e6),
        bandwidth_khz=radio.bandwidth_khz,
        interval_seconds=radio.spectral_scan_interval_seconds,
    )
    await service.start()
    ...
    await service.stop()
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional, Protocol

from src.api.telemetry.noise_floor import NoiseFloorTracker
from src.hal.sx1302_spectral_scan import SpectralScanResult

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SECONDS: float = 60.0
DEFAULT_STARTUP_DELAY_SECONDS: float = 10.0
DEFAULT_NB_SCAN: int = 1024


class _SupportsSpectralScan(Protocol):
    """Minimal interface ``SX1302Wrapper`` implements for this service."""

    @property
    def spectral_scan_supported(self) -> bool: ...

    def run_spectral_scan(
        self, frequency_hz: int, nb_scan: int = ...,
    ) -> Optional[SpectralScanResult]: ...


class SpectralScanService:
    """Periodic spectral-scan -> NoiseFloorTracker pump.

    Single-purpose: scheduling and result plumbing. The scan
    operation lives in ``SX1302SpectralScan`` and the value
    derivation lives in ``SpectralScanResult`` / ``NoiseFloorTracker``.
    """

    def __init__(
        self,
        wrapper: _SupportsSpectralScan,
        tracker: NoiseFloorTracker,
        frequency_hz: int,
        bandwidth_khz: float,
        interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
        startup_delay_seconds: float = DEFAULT_STARTUP_DELAY_SECONDS,
        nb_scan: int = DEFAULT_NB_SCAN,
    ) -> None:
        self._wrapper = wrapper
        self._tracker = tracker
        self._frequency_hz = frequency_hz
        self._bandwidth_khz = bandwidth_khz
        self._interval_seconds = max(5.0, interval_seconds)
        self._startup_delay_seconds = max(0.0, startup_delay_seconds)
        self._nb_scan = nb_scan
        self._task: Optional[asyncio.Task] = None
        self._stopped = asyncio.Event()
        self._scans_run = 0
        self._scans_failed = 0

    @property
    def scans_run(self) -> int:
        return self._scans_run

    @property
    def scans_failed(self) -> int:
        return self._scans_failed

    async def start(self) -> None:
        """Begin the periodic-scan loop.

        No-ops gracefully if the loaded HAL does not support
        spectral scan; the tracker stays in packet-derived mode.
        """
        if not self._wrapper.spectral_scan_supported:
            logger.info(
                "Spectral scan not supported by current libloragw; "
                "noise floor will use packet-derived fallback only",
            )
            return
        if self._task is not None:
            return
        self._stopped.clear()
        self._task = asyncio.get_running_loop().create_task(self._run_loop())
        logger.info(
            "SpectralScanService started: %.3f MHz, every %.0fs, "
            "first scan in %.0fs",
            self._frequency_hz / 1e6,
            self._interval_seconds,
            self._startup_delay_seconds,
        )

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stopped.set()
        self._task.cancel()
        try:
            await self._task
        except (asyncio.CancelledError, BaseException):
            pass
        self._task = None
        logger.info(
            "SpectralScanService stopped (scans=%d, failed=%d)",
            self._scans_run, self._scans_failed,
        )

    async def _run_loop(self) -> None:
        try:
            await asyncio.sleep(self._startup_delay_seconds)
            while not self._stopped.is_set():
                await self._scan_once()
                await asyncio.sleep(self._interval_seconds)
        except asyncio.CancelledError:
            raise

    async def _scan_once(self) -> None:
        try:
            result = await asyncio.to_thread(
                self._wrapper.run_spectral_scan,
                self._frequency_hz,
                self._nb_scan,
            )
        except Exception as exc:
            self._scans_failed += 1
            logger.warning("Spectral scan threw: %s", exc)
            return

        if result is None:
            self._scans_failed += 1
            return

        self._scans_run += 1
        self._publish(result)

    def _publish(self, result: SpectralScanResult) -> None:
        floor = result.floor_dbm
        median = result.median_dbm
        if floor is None or median is None:
            self._scans_failed += 1
            logger.warning(
                "Spectral scan returned empty histogram (samples=%d)",
                result.total_samples,
            )
            return
        self._tracker.update_from_spectral(
            floor_dbm=floor,
            median_dbm=median,
            frequency_hz=result.frequency_hz,
            bandwidth_khz=self._bandwidth_khz,
            samples=result.total_samples,
            timestamp=result.timestamp,
        )
        logger.debug(
            "Spectral scan: %.3f MHz floor=%.1f dBm median=%.1f dBm samples=%d",
            result.frequency_hz / 1e6, floor, median, result.total_samples,
        )
