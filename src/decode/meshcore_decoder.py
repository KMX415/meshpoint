"""Decodes raw Meshcore LoRa frames into structured Packet objects.

This is a stub module. The compiled core module (.so) overrides this
at runtime when meshpoint-core is installed.
"""

from __future__ import annotations

from typing import Optional

from src.decode.crypto_service import CryptoService
from src.models.node import Node
from src.models.packet import Packet
from src.models.signal import SignalMetrics
from src.models.telemetry import Telemetry

_CORE_MISSING = (
    "meshpoint-core is required for Meshcore decoding. "
    "See README.md for installation instructions."
)


class MeshcoreDecoder:
    """Decodes raw Meshcore LoRa frames into structured Packet objects.

    Requires the compiled meshpoint-core module.
    """

    def __init__(self, crypto: CryptoService):
        self._crypto = crypto

    def decode(
        self, raw_bytes: bytes, signal: Optional[SignalMetrics] = None
    ) -> Optional[Packet]:
        raise RuntimeError(_CORE_MISSING)

    def extract_node_update(self, packet: Packet) -> Optional[Node]:
        raise RuntimeError(_CORE_MISSING)

    def extract_telemetry(self, packet: Packet) -> Optional[Telemetry]:
        raise RuntimeError(_CORE_MISSING)
