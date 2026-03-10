"""Capture source for the RAK2287 SX1302 LoRa concentrator.

This is a stub module. The compiled core module (.so) overrides this
at runtime when meshpoint-core is installed.
"""

from __future__ import annotations

from typing import AsyncIterator

from src.capture.base import CaptureSource
from src.models.packet import RawCapture

_CORE_MISSING = (
    "meshpoint-core is required for concentrator capture. "
    "See README.md for installation instructions."
)


class ConcentratorCaptureSource(CaptureSource):
    """Captures LoRa packets via the RAK2287 SX1302 concentrator.

    Requires the compiled meshpoint-core module for actual hardware access.
    """

    def __init__(self, *args, **kwargs):
        raise RuntimeError(_CORE_MISSING)

    @property
    def name(self) -> str:
        return "concentrator"

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
