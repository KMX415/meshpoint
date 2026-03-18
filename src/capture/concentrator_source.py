"""Capture source for the RAK2287 SX1302 LoRa concentrator.

This is a stub module. The compiled core module (.so) overrides this
at runtime when meshpoint-core is installed.

Dual-protocol support
---------------------
When MeshCore reception is enabled (meshcore_radio.enabled=True), the
concentrator HAL is configured with separate sync words:

  - 8 multi-SF channels -> sync word 0x2B (Meshtastic)
  - 1 service channel   -> sync word 0x12 (MeshCore)

The SX1302 HAL tags each received packet with the demodulator index that
received it. The compiled core module uses this to set protocol_hint on
the RawCapture:

  - Packets from multi-SF demodulators -> protocol_hint = MESHTASTIC
  - Packets from the service channel   -> protocol_hint = MESHCORE

This hint is forwarded to PacketRouter.decode() so the correct decoder
is tried first.
"""

from __future__ import annotations

from typing import AsyncIterator, Optional

from src.capture.base import CaptureSource
from src.models.packet import Protocol, RawCapture

_CORE_MISSING = (
    "meshpoint-core is required for concentrator capture. "
    "See README.md for installation instructions."
)

SERVICE_CHANNEL_DEMOD_INDEX = 8


def protocol_hint_from_demod(demod_index: int, dual_protocol: bool) -> Optional[Protocol]:
    """Map SX1302 demodulator index to a protocol hint.

    The SX1302 has demodulators 0-7 for multi-SF and index 8 for the
    service channel. When dual-protocol mode is active, service channel
    packets are hinted as MeshCore.
    """
    if not dual_protocol:
        return None
    if demod_index == SERVICE_CHANNEL_DEMOD_INDEX:
        return Protocol.MESHCORE
    return Protocol.MESHTASTIC


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
