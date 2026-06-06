"""GPS reader for the ZOE-M8Q module on the RAK2287 HAT.

The GPS is accessed via the SX1302 HAL library's GPS functions,
or via the serial UART on the Pi (typically /dev/ttyAMA0).
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class GpsPosition:
    latitude: float
    longitude: float
    altitude: float
    satellites: int
    fix_quality: int
    timestamp: datetime


class GpsReader:
    """Reads GPS data from the ZOE-M8Q module on the RAK Pi HAT."""

    def __init__(self, uart_path: str = "/dev/ttyAMA0", baud: int = 9600):
        self._uart_path = uart_path
        self._baud = baud
        self._running = False
        self._latest: Optional[GpsPosition] = None
        self._task: Optional[asyncio.Task] = None

    @property
    def latest_position(self) -> Optional[GpsPosition]:
        return self._latest

    @property
    def has_fix(self) -> bool:
        return self._latest is not None and self._latest.fix_quality > 0

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(
            self._read_loop(), name="gps-reader"
        )
        logger.info("GPS reader started on %s", self._uart_path)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("GPS reader stopped")

    async def _read_loop(self) -> None:
        """Read NMEA sentences from the GPS UART.

        Linux device nodes (``/dev/tty*``) require pyserial; TCP-style
        ``asyncio.open_connection`` only applies to network hosts.
        """
        if self._uart_path.startswith("/dev/"):
            await self._fallback_loop()
            return

        try:
            reader, writer = await asyncio.open_connection(
                self._uart_path, self._baud
            )
        except Exception:
            logger.warning(
                "GPS UART not available at %s -- using serial fallback",
                self._uart_path,
            )
            await self._fallback_loop()
            return

        try:
            while self._running:
                line = await asyncio.wait_for(
                    reader.readline(), timeout=5.0
                )
                sentence = line.decode("ascii", errors="ignore").strip()
                self._parse_nmea(sentence)
        except asyncio.CancelledError:
            pass
        finally:
            writer.close()

    async def _fallback_loop(self) -> None:
        """Fallback: try reading GPS via serial library if available."""
        try:
            import serial

            ser = serial.Serial(self._uart_path, self._baud, timeout=2)
            while self._running:
                line = ser.readline().decode("ascii", errors="ignore").strip()
                if line:
                    self._parse_nmea(line)
                await asyncio.sleep(0.1)
        except ImportError:
            logger.warning("pyserial not installed, GPS unavailable")
            while self._running:
                await asyncio.sleep(10)
        except Exception:
            logger.exception("GPS fallback failed")

    def _parse_nmea(self, sentence: str) -> None:
        """Parse GGA sentences for position data."""
        if not sentence.startswith("$GPGGA") and not sentence.startswith("$GNGGA"):
            return

        try:
            parts = sentence.split(",")
            if len(parts) < 10:
                return

            fix_quality = int(parts[6]) if parts[6] else 0
            if fix_quality == 0:
                return

            lat = self._nmea_to_decimal(parts[2], parts[3])
            lon = self._nmea_to_decimal(parts[4], parts[5])
            alt = float(parts[9]) if parts[9] else 0.0
            sats = int(parts[7]) if parts[7] else 0

            self._latest = GpsPosition(
                latitude=lat,
                longitude=lon,
                altitude=alt,
                satellites=sats,
                fix_quality=fix_quality,
                timestamp=datetime.now(timezone.utc),
            )
        except (ValueError, IndexError):
            pass

    @staticmethod
    def _nmea_to_decimal(coord: str, direction: str) -> float:
        """Convert NMEA coordinate (ddmm.mmmm) to decimal degrees."""
        if not coord:
            return 0.0
        dot_pos = coord.index(".")
        degrees = float(coord[: dot_pos - 2])
        minutes = float(coord[dot_pos - 2 :])
        result = degrees + minutes / 60.0
        if direction in ("S", "W"):
            result = -result
        return round(result, 7)
