"""ctypes function signature setup for libloragw.

Extracted from ``sx1302_wrapper.py`` to keep that file focused on
the higher-level wrapper API rather than ABI bookkeeping. Spectral
scan signatures live in ``sx1302_spectral_scan.py`` since they are
opt-in (gracefully unavailable on older HAL builds).

Call ``apply_signatures(lib)`` once after ``ctypes.CDLL(libpath)``
and before any other call into the loaded library.
"""
from __future__ import annotations

import ctypes

from src.hal.sx1302_types import (
    LgwConfBoardS,
    LgwConfRxifS,
    LgwConfRxrfS,
    LgwConfSx1261S,
    LgwPktRxS,
    LgwPktTxS,
    LgwTxGainLutS,
)


def apply_signatures(lib: ctypes.CDLL) -> None:
    """Set restype/argtypes on every libloragw function we call.

    Mismatched ctypes signatures on a 64-bit platform produce truly
    nasty silent corruption (pointer truncation, sign-extension
    bugs); this is the single source of truth for the surface area
    used by ``SX1302Wrapper``.
    """
    lib.lgw_board_setconf.restype = ctypes.c_int
    lib.lgw_board_setconf.argtypes = [ctypes.POINTER(LgwConfBoardS)]

    lib.lgw_rxrf_setconf.restype = ctypes.c_int
    lib.lgw_rxrf_setconf.argtypes = [
        ctypes.c_uint8,
        ctypes.POINTER(LgwConfRxrfS),
    ]

    lib.lgw_rxif_setconf.restype = ctypes.c_int
    lib.lgw_rxif_setconf.argtypes = [
        ctypes.c_uint8,
        ctypes.POINTER(LgwConfRxifS),
    ]

    lib.lgw_start.restype = ctypes.c_int
    lib.lgw_start.argtypes = []

    lib.lgw_stop.restype = ctypes.c_int
    lib.lgw_stop.argtypes = []

    lib.lgw_receive.restype = ctypes.c_int
    lib.lgw_receive.argtypes = [
        ctypes.c_uint8,
        ctypes.POINTER(LgwPktRxS),
    ]

    lib.sx1302_lora_syncword.restype = ctypes.c_int
    lib.sx1302_lora_syncword.argtypes = [
        ctypes.c_bool,
        ctypes.c_uint8,
    ]

    lib.lgw_txgain_setconf.restype = ctypes.c_int
    lib.lgw_txgain_setconf.argtypes = [
        ctypes.c_uint8,
        ctypes.POINTER(LgwTxGainLutS),
    ]

    lib.lgw_send.restype = ctypes.c_int
    lib.lgw_send.argtypes = [ctypes.POINTER(LgwPktTxS)]

    lib.lgw_status.restype = ctypes.c_int
    lib.lgw_status.argtypes = [
        ctypes.c_uint8,
        ctypes.c_uint8,
        ctypes.POINTER(ctypes.c_uint8),
    ]

    lib.lgw_abort_tx.restype = ctypes.c_int
    lib.lgw_abort_tx.argtypes = [ctypes.c_uint8]

    lib.lgw_time_on_air.restype = ctypes.c_uint32
    lib.lgw_time_on_air.argtypes = [ctypes.POINTER(LgwPktTxS)]

    if hasattr(lib, "lgw_sx1261_setconf"):
        lib.lgw_sx1261_setconf.restype = ctypes.c_int
        lib.lgw_sx1261_setconf.argtypes = [ctypes.POINTER(LgwConfSx1261S)]
