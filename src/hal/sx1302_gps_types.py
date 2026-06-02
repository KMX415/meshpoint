"""ctypes mirrors of loragw_gps.h structures for PPS time sync."""

from __future__ import annotations

import ctypes


class TimespecS(ctypes.Structure):
    """``struct timespec`` as used by the HAL GPS module."""

    _fields_ = [
        ("tv_sec", ctypes.c_long),
        ("tv_nsec", ctypes.c_long),
    ]


class TrefS(ctypes.Structure):
    """``struct tref`` — concentrator counter to GPS/UTC mapping."""

    _fields_ = [
        ("systime", ctypes.c_long),
        ("count_us", ctypes.c_uint32),
        ("utc", TimespecS),
        ("gps", TimespecS),
        ("xtal_err", ctypes.c_double),
    ]


class CoordS(ctypes.Structure):
    """``struct coord_s`` — geodesic coordinates from NMEA/UBX."""

    _fields_ = [
        ("lat", ctypes.c_double),
        ("lon", ctypes.c_double),
        ("alt", ctypes.c_short),
    ]


# loragw_gps.h
LGW_GPS_SUCCESS = 0
LGW_GPS_ERROR = -1

# gps_msg enum subset used after parse
GPS_MSG_UNKNOWN = 0
GPS_MSG_UBX_NAV_TIMEGPS = 13
