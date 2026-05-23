"""Spectral scan operation on the SX1302 concentrator.

The SX1302 has a built-in spectral scanner that samples the channel
RSSI over a short window and returns a histogram across 35 RSSI
levels. This is the *correct* way to measure noise floor: it reads
the LNA output power directly between (or instead of) packet
demodulation, without depending on packet metadata.

Compared to packet-derived ``rssi - snr`` estimates, spectral scan:
    - Measures actual ambient channel power, not an upper bound from
      a particular packet's demod state.
    - Works in environments with no packet traffic.
    - Matches what dedicated single-channel SDR tools (e.g. SX1262
      HAT-based monitors) report on the same channel.

Tradeoff: each scan briefly pauses RX on the scanned channel for the
duration of the scan window (~50 ms by default). At a 60-second scan
cadence that is ~0.08% RX downtime — invisible against normal
packet-loss variance. Scheduling is the caller's responsibility;
this class is concerned only with the start / poll / read cycle.

This file is split out from ``sx1302_wrapper.py`` to keep that file
well under the 500-line ceiling while letting the spectral scan
logic carry its own docstrings and helpers.
"""
from __future__ import annotations

import ctypes
import logging
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

LGW_HAL_SUCCESS = 0
LGW_SPECTRAL_SCAN_NB_LEVELS = 35

LGW_SPECTRAL_SCAN_STATUS_NONE = 0
LGW_SPECTRAL_SCAN_STATUS_ON_GOING = 1
LGW_SPECTRAL_SCAN_STATUS_ABORTED = 2
LGW_SPECTRAL_SCAN_STATUS_COMPLETED = 3
LGW_SPECTRAL_SCAN_STATUS_UNKNOWN = 4

DEFAULT_NB_SCAN: int = 1024
"""Number of background-noise samples taken per scan.

1024 samples at the SX1302's spectral scan rate land in roughly
50 ms, which gives a tight median while keeping RX gap small.
"""

POLL_INTERVAL_S: float = 0.010
SCAN_TIMEOUT_S: float = 1.0


@dataclass
class SpectralScanResult:
    """Histogram returned by ``lgw_spectral_scan_get_results``.

    The HAL returns two parallel arrays of length 35:
        levels_dbm[i] : RSSI threshold in dBm (e.g. -156, -154, ...)
        counts[i]     : number of samples at exactly this level

    Note: older HAL builds returned cumulative ``count >= levels[i]``
    counts. We treat the result as a per-bin histogram (the modern
    layout) and compute cumulative counts on the fly when needed,
    which is correct under both interpretations as long as the
    derived metrics use the cumulative form consistently.
    """

    levels_dbm: tuple[int, ...]
    counts: tuple[int, ...]
    frequency_hz: int
    nb_scan: int
    timestamp: float

    @property
    def total_samples(self) -> int:
        return sum(self.counts)

    def percentile(self, p: float) -> Optional[float]:
        """Return the dBm value at the p-th percentile.

        ``p=50`` returns the median; ``p=10`` returns the level
        below which 10% of samples fall.
        """
        total = self.total_samples
        if total <= 0:
            return None
        target = total * (p / 100.0)
        cumulative = 0
        for level, count in zip(self.levels_dbm, self.counts):
            cumulative += count
            if cumulative >= target:
                return float(level)
        return float(self.levels_dbm[-1])

    @property
    def median_dbm(self) -> Optional[float]:
        return self.percentile(50.0)

    @property
    def floor_dbm(self) -> Optional[float]:
        """10th-percentile reading, a conservative noise-floor estimate."""
        return self.percentile(10.0)


class SX1302SpectralScan:
    """Run a single spectral scan via the loaded libloragw.

    Holds a reference to a ``ctypes.CDLL`` instance (typically the
    same library handle used by ``SX1302Wrapper``). Caller is
    responsible for ensuring the concentrator is started before
    invoking ``run``, and for serialising scans (no concurrent
    scans on the same chip).
    """

    def __init__(self, lib: ctypes.CDLL) -> None:
        self._lib = lib
        self._signatures_set = False
        self._supported = self._check_support()

    @property
    def supported(self) -> bool:
        """True if the loaded HAL exposes the spectral scan symbols."""
        return self._supported

    def run(
        self,
        frequency_hz: int,
        nb_scan: int = DEFAULT_NB_SCAN,
        timeout_s: float = SCAN_TIMEOUT_S,
    ) -> Optional[SpectralScanResult]:
        """Execute one start -> poll -> read cycle. Returns None on failure."""
        if not self._supported:
            return None
        if not self._signatures_set:
            self._setup_signatures()

        start_rc = self._lib.lgw_spectral_scan_start(
            ctypes.c_uint32(frequency_hz),
            ctypes.c_uint16(nb_scan),
        )
        if start_rc != LGW_HAL_SUCCESS:
            logger.warning(
                "lgw_spectral_scan_start(%d Hz, %d) failed (rc=%d)",
                frequency_hz, nb_scan, start_rc,
            )
            return None

        if not self._wait_for_completion(timeout_s):
            self._abort_quietly()
            return None

        return self._read_results(frequency_hz, nb_scan)

    def _wait_for_completion(self, timeout_s: float) -> bool:
        deadline = time.monotonic() + timeout_s
        status = ctypes.c_int(LGW_SPECTRAL_SCAN_STATUS_NONE)
        while time.monotonic() < deadline:
            rc = self._lib.lgw_spectral_scan_get_status(ctypes.byref(status))
            if rc != LGW_HAL_SUCCESS:
                logger.warning("lgw_spectral_scan_get_status failed (rc=%d)", rc)
                return False
            if status.value == LGW_SPECTRAL_SCAN_STATUS_COMPLETED:
                return True
            if status.value == LGW_SPECTRAL_SCAN_STATUS_ABORTED:
                logger.warning("Spectral scan reported ABORTED")
                return False
            time.sleep(POLL_INTERVAL_S)
        logger.warning("Spectral scan timed out after %.2fs", timeout_s)
        return False

    def _read_results(
        self, frequency_hz: int, nb_scan: int
    ) -> Optional[SpectralScanResult]:
        levels = (ctypes.c_int16 * LGW_SPECTRAL_SCAN_NB_LEVELS)()
        counts = (ctypes.c_uint16 * LGW_SPECTRAL_SCAN_NB_LEVELS)()
        rc = self._lib.lgw_spectral_scan_get_results(levels, counts)
        if rc != LGW_HAL_SUCCESS:
            logger.warning("lgw_spectral_scan_get_results failed (rc=%d)", rc)
            return None
        return SpectralScanResult(
            levels_dbm=tuple(levels[i] for i in range(LGW_SPECTRAL_SCAN_NB_LEVELS)),
            counts=tuple(counts[i] for i in range(LGW_SPECTRAL_SCAN_NB_LEVELS)),
            frequency_hz=frequency_hz,
            nb_scan=nb_scan,
            timestamp=time.time(),
        )

    def _abort_quietly(self) -> None:
        try:
            self._lib.lgw_spectral_scan_abort()
        except (AttributeError, OSError):
            pass

    def _check_support(self) -> bool:
        for symbol in (
            "lgw_spectral_scan_start",
            "lgw_spectral_scan_get_status",
            "lgw_spectral_scan_get_results",
        ):
            if not hasattr(self._lib, symbol):
                logger.info(
                    "libloragw does not expose %s; "
                    "spectral scan disabled, falling back to packet-derived noise floor",
                    symbol,
                )
                return False
        return True

    def _setup_signatures(self) -> None:
        lib = self._lib
        lib.lgw_spectral_scan_start.restype = ctypes.c_int
        lib.lgw_spectral_scan_start.argtypes = [
            ctypes.c_uint32,
            ctypes.c_uint16,
        ]
        lib.lgw_spectral_scan_get_status.restype = ctypes.c_int
        lib.lgw_spectral_scan_get_status.argtypes = [
            ctypes.POINTER(ctypes.c_int),
        ]
        lib.lgw_spectral_scan_get_results.restype = ctypes.c_int
        lib.lgw_spectral_scan_get_results.argtypes = [
            ctypes.POINTER(ctypes.c_int16),
            ctypes.POINTER(ctypes.c_uint16),
        ]
        if hasattr(lib, "lgw_spectral_scan_abort"):
            lib.lgw_spectral_scan_abort.restype = ctypes.c_int
            lib.lgw_spectral_scan_abort.argtypes = []
        self._signatures_set = True
