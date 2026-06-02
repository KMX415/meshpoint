"""UART location source: on-board NMEA GPS (RAK Pi HAT /dev/ttyAMA0).

Wraps ``GpsReader`` so the coordinator and ``GET /api/device/gps-status``
share the same ``LocationSource`` contract as gpsd. Skyplot az/el/SNR
requires GSV sentences (not parsed yet); GGA provides fix + satellite
count only.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from src.hal.gps_reader import GpsReader, GpsPosition
from src.hal.location.base import LocationSource
from src.hal.location.models import (
    GpsDeviceInfo,
    GpsStatus,
    LocationFix,
    SatellitesView,
)

logger = logging.getLogger(__name__)


def _gga_fix_mode(fix_quality: int) -> int:
    """Map NMEA GGA fix quality to gpsd-style mode (2=2D, 3=3D)."""
    if fix_quality >= 2:
        return 3
    if fix_quality == 1:
        return 2
    return 1


def _min_gga_quality(min_fix_quality: int) -> int:
    """Translate LocationConfig min_fix_quality to minimum GGA fix_quality.

    Config uses gpsd semantics: 1=2D, 2=3D. GGA uses 0=no fix, 1=GPS,
    2=DGPS, etc. We accept any non-zero GGA fix when min is 1, and
    require GGA fix_quality >= 2 when min is 2.
    """
    if min_fix_quality >= 2:
        return 2
    return 1


class UartSource(LocationSource):
    """Live fixes from a serial NMEA GPS on the Pi UART."""

    def __init__(
        self,
        uart_path: str = "/dev/ttyAMA0",
        baud: int = 9600,
        min_fix_quality: int = 1,
    ) -> None:
        self._uart_path = uart_path
        self._baud = baud
        self._min_fix_quality = min_fix_quality
        self._reader: Optional[GpsReader] = None
        self._started = False
        self._last_error: Optional[str] = None

    @property
    def source_name(self) -> str:
        return "uart"

    async def start(self) -> None:
        if self._reader is not None:
            return
        self._reader = GpsReader(uart_path=self._uart_path, baud=self._baud)
        await self._reader.start()
        self._started = True
        self._last_error = None
        logger.info(
            "UART location source: reading NMEA from %s @ %d baud",
            self._uart_path,
            self._baud,
        )

    async def stop(self) -> None:
        if self._reader is None:
            return
        await self._reader.stop()
        self._reader = None
        self._started = False

    def get_status(self) -> GpsStatus:
        now = datetime.now(timezone.utc)
        device = GpsDeviceInfo(
            driver="nmea",
            path=self._uart_path,
            model="RAK Pi HAT GPS",
            subtype=f"{self._baud} baud",
        )

        if not self._started or self._reader is None:
            return GpsStatus(
                source="uart",
                available=False,
                device=device,
                error=self._last_error or "UART reader not started",
                last_update=now,
            )

        pos = self._reader.latest_position
        if pos is None or not self._position_meets_quality(pos):
            return GpsStatus(
                source="uart",
                available=True,
                device=device,
                error=None,
                last_update=now,
            )

        return GpsStatus(
            source="uart",
            available=True,
            fix=self._position_to_fix(pos),
            satellites=self._satellites_from_position(pos),
            device=device,
            last_update=pos.timestamp,
        )

    def _position_meets_quality(self, pos: GpsPosition) -> bool:
        return pos.fix_quality >= _min_gga_quality(self._min_fix_quality)

    @staticmethod
    def _position_to_fix(pos: GpsPosition) -> LocationFix:
        return LocationFix(
            mode=_gga_fix_mode(pos.fix_quality),
            latitude=pos.latitude,
            longitude=pos.longitude,
            altitude_m=pos.altitude,
            time=pos.timestamp,
        )

    @staticmethod
    def _satellites_from_position(pos: GpsPosition) -> SatellitesView:
        count = max(0, pos.satellites)
        return SatellitesView(in_view=count, used=count, satellites=())
