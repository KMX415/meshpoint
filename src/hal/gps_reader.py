"""GPS reader for the ZOE-M8Q module on the RAK2287 HAT.

This is a stub module. The compiled core module (.so) overrides this
at runtime when meshpoint-core is installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

_CORE_MISSING = (
    "meshpoint-core is required for GPS functionality. "
    "See README.md for installation instructions."
)


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
        raise RuntimeError(_CORE_MISSING)
