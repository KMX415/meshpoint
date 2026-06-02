"""ctypes signatures for libloragw GPS/PPS functions (loragw_gps.h)."""

from __future__ import annotations

import ctypes

from src.hal.sx1302_gps_types import CoordS, TrefS, TimespecS


def apply_gps_signatures(lib: ctypes.CDLL) -> None:
    """Register optional GPS symbols when present in libloragw.so."""
    if hasattr(lib, "lgw_gps_enable"):
        lib.lgw_gps_enable.restype = ctypes.c_int
        lib.lgw_gps_enable.argtypes = [
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_uint,
            ctypes.POINTER(ctypes.c_int),
        ]

    if hasattr(lib, "lgw_gps_disable"):
        lib.lgw_gps_disable.restype = ctypes.c_int
        lib.lgw_gps_disable.argtypes = [ctypes.c_int]

    if hasattr(lib, "lgw_parse_nmea"):
        lib.lgw_parse_nmea.restype = ctypes.c_int
        lib.lgw_parse_nmea.argtypes = [ctypes.c_char_p, ctypes.c_int]

    if hasattr(lib, "lgw_parse_ubx"):
        lib.lgw_parse_ubx.restype = ctypes.c_int
        lib.lgw_parse_ubx.argtypes = [
            ctypes.c_char_p,
            ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_size_t),
        ]

    if hasattr(lib, "lgw_gps_get"):
        lib.lgw_gps_get.restype = ctypes.c_int
        lib.lgw_gps_get.argtypes = [
            ctypes.POINTER(TimespecS),
            ctypes.POINTER(TimespecS),
            ctypes.POINTER(CoordS),
            ctypes.POINTER(CoordS),
        ]

    if hasattr(lib, "lgw_gps_sync"):
        lib.lgw_gps_sync.restype = ctypes.c_int
        lib.lgw_gps_sync.argtypes = [
            ctypes.POINTER(TrefS),
            ctypes.c_uint32,
            TimespecS,
            TimespecS,
        ]

    if hasattr(lib, "lgw_get_trigcnt"):
        lib.lgw_get_trigcnt.restype = ctypes.c_int
        lib.lgw_get_trigcnt.argtypes = [ctypes.POINTER(ctypes.c_uint32)]

    if hasattr(lib, "lgw_cnt2utc"):
        lib.lgw_cnt2utc.restype = ctypes.c_int
        lib.lgw_cnt2utc.argtypes = [
            TrefS,
            ctypes.c_uint32,
            ctypes.POINTER(TimespecS),
        ]

    if hasattr(lib, "sx1302_gps_enable"):
        lib.sx1302_gps_enable.restype = ctypes.c_int
        lib.sx1302_gps_enable.argtypes = [ctypes.c_bool]
