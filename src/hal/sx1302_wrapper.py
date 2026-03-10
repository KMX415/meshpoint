"""ctypes wrapper for the Semtech SX1302 HAL (libloragw).

This is a stub module. The compiled core module (.so) shipped alongside
this file overrides it at runtime. If you see an error from this file,
the .so binary may be missing -- reinstall from the meshpoint release.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

_CORE_MISSING = (
    "meshpoint-core is required for concentrator operation. "
    "See README.md for installation instructions."
)

BW_125KHZ = 0x04
BW_250KHZ = 0x05
BW_500KHZ = 0x06
BW_MAP = {BW_125KHZ: 125.0, BW_250KHZ: 250.0, BW_500KHZ: 500.0}


@dataclass
class ConcentratorPacket:
    """Decoded packet from the concentrator hardware."""

    payload: bytes
    frequency_hz: int
    rssi: float
    snr: float
    spreading_factor: int
    bandwidth: int
    coderate: int
    crc_ok: bool
    timestamp_us: int


class SX1302Wrapper:
    """Python interface to the SX1302 concentrator via libloragw.

    Requires the compiled meshpoint-core module for actual hardware access.
    """

    def __init__(
        self,
        lib_path: Optional[str] = None,
        spi_path: str = "/dev/spidev0.0",
    ):
        raise RuntimeError(_CORE_MISSING)
