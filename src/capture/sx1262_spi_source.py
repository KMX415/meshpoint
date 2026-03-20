"""Optional capture source for Waveshare SX1262 (SPI) — MeshCore RX path.

This is a stub module. The compiled meshpoint-core module (`.so`) overrides
this at runtime when meshpoint-core is installed.
"""

from __future__ import annotations

from typing import AsyncIterator

from src.capture.base import CaptureSource
from src.models.packet import RawCapture

_CORE_MISSING = (
    "meshpoint-core is required for SX1262 SPI capture. "
    "See README.md for installation instructions."
)


class Sx1262SpiCaptureSource(CaptureSource):
    """Captures MeshCore LoRa frames via the Waveshare SX1262 HAT (SPI).

    Requires the compiled meshpoint-core module for actual hardware access.
    """

    def __init__(self, *args, **kwargs):
        raise RuntimeError(_CORE_MISSING)

    @property
    def name(self) -> str:
        return "sx1262_spi"

    @property
    def is_running(self) -> bool:
        return False

    async def start(self) -> None:
        raise RuntimeError(_CORE_MISSING)

    async def stop(self) -> None:
        pass

    async def packets(self) -> AsyncIterator[RawCapture]:
        raise RuntimeError(_CORE_MISSING)
        yield  # pragma: no cover
