"""ctypes bindings for the SX1302 HAL spectral scan API.

The spectral scan is driven by the SX1261 companion radio (separate chip
from SX1302) so it can run concurrently with packet reception, but SX1261
access must be serialized with TX operations via a shared asyncio.Lock.

HAL constants:
    LGW_SPECTRAL_SCAN_RESULT_SIZE = 33   (frequency bins per scan step)
    LGW_HAL_SUCCESS = 0

Status codes returned by lgw_spectral_scan_get_status:
    NONE      = 0
    ON_GOING  = 1
    ABORTED   = 2
    COMPLETED = 3
"""

from __future__ import annotations

import ctypes
import ctypes.util
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

RESULT_SIZE = 33

STATUS_NONE = 0
STATUS_ON_GOING = 1
STATUS_ABORTED = 2
STATUS_COMPLETED = 3

LGW_HAL_SUCCESS = 0

_lib: ctypes.CDLL | None = None


def _load_lib() -> ctypes.CDLL | None:
    global _lib
    if _lib is not None:
        return _lib

    candidates = [
        "/usr/local/lib/libloragw.so",
        "/usr/lib/libloragw.so",
        "/opt/meshpoint/libloragw.so",
    ]
    found = ctypes.util.find_library("loragw")
    if found:
        candidates.insert(0, found)

    for path in candidates:
        if Path(path).exists():
            try:
                _lib = ctypes.CDLL(path)
                _configure_signatures(_lib)
                logger.info("Loaded libloragw from %s", path)
                return _lib
            except OSError as exc:
                logger.debug("Failed to load %s: %s", path, exc)

    logger.warning("libloragw not found — spectral scan unavailable")
    return None


def _configure_signatures(lib: ctypes.CDLL) -> None:
    lib.lgw_spectral_scan_start.argtypes = [ctypes.c_uint32, ctypes.c_uint16]
    lib.lgw_spectral_scan_start.restype = ctypes.c_int

    lib.lgw_spectral_scan_get_status.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
    lib.lgw_spectral_scan_get_status.restype = ctypes.c_int

    lib.lgw_spectral_scan_get_results.argtypes = [
        ctypes.POINTER(ctypes.c_int8 * RESULT_SIZE),
        ctypes.POINTER(ctypes.c_uint16 * RESULT_SIZE),
    ]
    lib.lgw_spectral_scan_get_results.restype = ctypes.c_int

    lib.lgw_spectral_scan_abort.argtypes = []
    lib.lgw_spectral_scan_abort.restype = ctypes.c_int


def is_available() -> bool:
    return _load_lib() is not None


def scan_start(freq_hz: int, nb_scan: int = 2000) -> bool:
    lib = _load_lib()
    if lib is None:
        return False
    rc = lib.lgw_spectral_scan_start(ctypes.c_uint32(freq_hz), ctypes.c_uint16(nb_scan))
    return rc == LGW_HAL_SUCCESS


def scan_get_status() -> int:
    lib = _load_lib()
    if lib is None:
        return STATUS_NONE
    status = ctypes.c_uint8(0)
    lib.lgw_spectral_scan_get_status(ctypes.byref(status))
    return status.value


def scan_get_results() -> tuple[list[int], list[int]]:
    """Return (levels_dbm[33], counts[33]) from the last completed scan."""
    lib = _load_lib()
    if lib is None:
        return [], []
    levels = (ctypes.c_int8 * RESULT_SIZE)()
    counts = (ctypes.c_uint16 * RESULT_SIZE)()
    rc = lib.lgw_spectral_scan_get_results(
        ctypes.byref(levels), ctypes.byref(counts)
    )
    if rc != LGW_HAL_SUCCESS:
        return [], []
    return list(levels), list(counts)


def scan_abort() -> None:
    lib = _load_lib()
    if lib is not None:
        lib.lgw_spectral_scan_abort()


def peak_rssi(levels: list[int], counts: list[int]) -> int | None:
    """Return the highest level_dbm bin where count > 0, or None."""
    best: int | None = None
    for lvl, cnt in zip(levels, counts):
        if cnt > 0 and (best is None or lvl > best):
            best = lvl
    return best
