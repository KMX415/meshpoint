"""UART location source: placeholder for direct on-board NMEA reading.

The existing ``src.hal.gps_reader.GpsReader`` (created during the v0.4.x
multi-region work but never wired into the runtime) parses NMEA from a
serial port and exposes ``current_position``. Wiring it through the
``LocationSource`` contract is a follow-on item: probably v0.7.6 or
when a user actually reports they want to use the RAK Pi HAT's
on-board u-blox.

For v0.7.5 this source returns ``available=False`` with an explanatory
error so the GPS card surfaces the correct "not yet implemented"
message instead of falling silently to zero coordinates.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.hal.location.base import LocationSource
from src.hal.location.models import GpsStatus

logger = logging.getLogger(__name__)


class UartSource(LocationSource):
    """Reserved location source for on-board UART GPS (RAK Pi HAT etc.)."""

    @property
    def source_name(self) -> str:
        return "uart"

    async def start(self) -> None:
        logger.info(
            "UART location source: not yet wired -- using static "
            "device coordinates as fallback"
        )

    async def stop(self) -> None:
        return

    def get_status(self) -> GpsStatus:
        return GpsStatus(
            source="uart",
            available=False,
            error=(
                "UART GPS source is reserved for the RAK Pi HAT on-board "
                "module and is not yet wired into the runtime. Switch to "
                "'static' or 'gpsd' under Configuration -> GPS."
            ),
            last_update=datetime.now(timezone.utc),
        )
