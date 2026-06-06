"""Semtech libloragw GPS/PPS time synchronization (lgw_gps_* bindings).

Aligns the SX1302/SX1303 internal packet counter with GPS time using
the HAL's serial parser and ``lgw_gps_sync``. This is separate from
``location.source: uart`` / ``gpsd``, which only feed dashboard
coordinates — PPS sync is for accurate ``timestamp_us`` on RX packets.

Typical RAK Pi HAT wiring: u-blox on ``/dev/ttyAMA0``, PPS into the
concentrator. Do not enable PPS and ``location.source: uart`` on the
same TTY simultaneously (exclusive open).
"""

from __future__ import annotations

import ctypes
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from src.hal.sx1302_gps_types import (
    CoordS,
    GPS_MSG_UBX_NAV_TIMEGPS,
    LGW_GPS_ERROR,
    LGW_GPS_SUCCESS,
    TrefS,
    TimespecS,
)

if TYPE_CHECKING:
    from ctypes import CDLL

logger = logging.getLogger(__name__)

LGW_HAL_SUCCESS = 0
_READ_CHUNK = 256
_PARSE_BUF = 4096


@dataclass
class GpsPpsStatus:
    """Runtime snapshot for dashboards and ``GET /api/device/gps-pps-status``."""

    enabled: bool
    available: bool
    tty_path: str
    gps_family: str
    sync_count: int
    last_sync_ok: bool
    last_error: Optional[str] = None
    xtal_err: Optional[float] = None
    reference_count_us: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "available": self.available,
            "tty_path": self.tty_path,
            "gps_family": self.gps_family,
            "sync_count": self.sync_count,
            "last_sync_ok": self.last_sync_ok,
            "last_error": self.last_error,
            "xtal_err": self.xtal_err,
            "reference_count_us": self.reference_count_us,
        }


class HalGpsPpsSync:
    """Background GPS reader + periodic ``lgw_gps_sync`` against PPS."""

    def __init__(
        self,
        lib: CDLL,
        tty_path: str = "/dev/ttyAMA0",
        gps_family: str = "ubx7",
        target_baud: int = 0,
    ) -> None:
        self._lib = lib
        self._tty_path = tty_path
        self._gps_family = gps_family
        self._target_baud = target_baud
        self._fd: int = -1
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._ref = TrefS()
        self._ref.systime = 0
        self._sync_count = 0
        self._last_sync_ok = False
        self._last_error: Optional[str] = None
        self._enabled = False

    @property
    def supported(self) -> bool:
        return hasattr(self._lib, "lgw_gps_enable") and hasattr(
            self._lib, "lgw_gps_sync"
        )

    def get_status(self) -> GpsPpsStatus:
        with self._lock:
            return GpsPpsStatus(
                enabled=self._enabled,
                available=self._fd >= 0 and self.supported,
                tty_path=self._tty_path,
                gps_family=self._gps_family,
                sync_count=self._sync_count,
                last_sync_ok=self._last_sync_ok,
                last_error=self._last_error,
                xtal_err=self._ref.xtal_err if self._last_sync_ok else None,
                reference_count_us=(
                    int(self._ref.count_us) if self._last_sync_ok else None
                ),
            )

    def start(self) -> bool:
        """Open GPS UART via HAL and enable SX1302 PPS sampling if available."""
        if not self.supported:
            self._last_error = "libloragw lacks lgw_gps_enable/lgw_gps_sync"
            logger.info("GPS/PPS sync unavailable: %s", self._last_error)
            return False

        if self._enabled:
            return True

        fd = ctypes.c_int(-1)
        tty_b = self._tty_path.encode("ascii")
        family_b = self._gps_family.encode("ascii")
        baud = self._target_baud
        if hasattr(self._lib, "lgw_gps_enable"):
            try:
                from termios import B9600

                if baud == 0:
                    baud = B9600
            except ImportError:
                if baud == 0:
                    baud = 13  # B9600 on Linux; Pi-only path

        rc = self._lib.lgw_gps_enable(
            tty_b, family_b, ctypes.c_uint(baud), ctypes.byref(fd)
        )
        if rc != LGW_GPS_SUCCESS:
            self._last_error = f"lgw_gps_enable({self._tty_path}) failed (rc={rc})"
            logger.warning("GPS/PPS: %s", self._last_error)
            return False

        self._fd = int(fd.value)
        if hasattr(self._lib, "sx1302_gps_enable"):
            sx_rc = self._lib.sx1302_gps_enable(True)
            if sx_rc != LGW_HAL_SUCCESS:
                logger.warning(
                    "sx1302_gps_enable(true) returned %s (PPS may be unavailable)",
                    sx_rc,
                )

        self._stop.clear()
        self._thread = threading.Thread(
            target=self._reader_loop,
            name="hal-gps-pps",
            daemon=True,
        )
        self._thread.start()
        self._enabled = True
        logger.info(
            "GPS/PPS sync started (tty=%s family=%s fd=%d)",
            self._tty_path,
            self._gps_family,
            self._fd,
        )
        return True

    def stop(self) -> None:
        if not self._enabled:
            return
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None

        if self._fd >= 0 and hasattr(self._lib, "lgw_gps_disable"):
            self._lib.lgw_gps_disable(self._fd)
        self._fd = -1

        if hasattr(self._lib, "sx1302_gps_enable"):
            self._lib.sx1302_gps_enable(False)

        self._enabled = False
        logger.info("GPS/PPS sync stopped")

    def convert_timestamp_us_to_utc(
        self, count_us: int
    ) -> Optional[tuple[int, int]]:
        """Return (tv_sec, tv_nsec) UTC for a concentrator counter, if synced."""
        if not self._last_sync_ok or not hasattr(self._lib, "lgw_cnt2utc"):
            return None
        utc = TimespecS()
        with self._lock:
            ref_copy = TrefS()
            ctypes.memmove(
                ctypes.byref(ref_copy),
                ctypes.byref(self._ref),
                ctypes.sizeof(TrefS),
            )
        rc = self._lib.lgw_cnt2utc(ref_copy, count_us, ctypes.byref(utc))
        if rc != LGW_GPS_SUCCESS:
            return None
        return int(utc.tv_sec), int(utc.tv_nsec)

    def _reader_loop(self) -> None:
        parse_buf = bytearray()
        while not self._stop.is_set():
            if self._fd < 0:
                time.sleep(0.5)
                continue
            try:
                chunk = os.read(self._fd, _READ_CHUNK)
            except OSError as exc:
                self._last_error = f"GPS read failed: {exc}"
                time.sleep(1.0)
                continue

            if not chunk:
                time.sleep(0.05)
                continue

            parse_buf.extend(chunk)
            if len(parse_buf) > _PARSE_BUF:
                del parse_buf[: len(parse_buf) - _PARSE_BUF]

            self._consume_parse_buffer(parse_buf)

    def _consume_parse_buffer(self, buf: bytearray) -> None:
        if not buf:
            return

        text = bytes(buf).decode("ascii", errors="ignore")
        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("$"):
                with self._lock:
                    if hasattr(self._lib, "lgw_parse_nmea"):
                        self._lib.lgw_parse_nmea(
                            line.encode("ascii"),
                            len(line) + 1,
                        )

        if hasattr(self._lib, "lgw_parse_ubx"):
            msg_size = ctypes.c_size_t(0)
            raw = bytes(buf)
            with self._lock:
                msg = self._lib.lgw_parse_ubx(
                    raw,
                    len(raw),
                    ctypes.byref(msg_size),
                )
            if msg == GPS_MSG_UBX_NAV_TIMEGPS:
                self._attempt_sync()

    def _attempt_sync(self) -> None:
        utc = TimespecS()
        gps_time = TimespecS()
        with self._lock:
            if hasattr(self._lib, "lgw_gps_get"):
                rc_get = self._lib.lgw_gps_get(
                    ctypes.byref(utc),
                    ctypes.byref(gps_time),
                    None,
                    None,
                )
            else:
                return
        if rc_get != LGW_GPS_SUCCESS:
            return

        count_us = ctypes.c_uint32(0)
        if hasattr(self._lib, "lgw_get_trigcnt"):
            rc_cnt = self._lib.lgw_get_trigcnt(ctypes.byref(count_us))
            if rc_cnt != LGW_HAL_SUCCESS:
                self._last_error = "lgw_get_trigcnt failed before gps_sync"
                return

        with self._lock:
            rc = self._lib.lgw_gps_sync(
                ctypes.byref(self._ref),
                count_us.value,
                utc,  # struct passed by value per loragw_gps.h
                gps_time,
            )

        self._sync_count += 1
        if rc == LGW_GPS_SUCCESS:
            self._last_sync_ok = True
            self._last_error = None
            if self._sync_count == 1 or self._sync_count % 60 == 0:
                logger.info(
                    "GPS/PPS sync #%d ok (count_us=%u xtal_err=%.9f)",
                    self._sync_count,
                    count_us.value,
                    self._ref.xtal_err,
                )
        else:
            self._last_sync_ok = False
            self._last_error = f"lgw_gps_sync returned {rc}"
