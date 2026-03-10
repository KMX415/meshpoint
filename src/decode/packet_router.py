"""Routes raw captured bytes to the appropriate protocol decoder.

This is a stub module. The compiled core module (.so) overrides this
at runtime when meshpoint-core is installed.
"""

from __future__ import annotations

from typing import Optional

from src.decode.crypto_service import CryptoService
from src.decode.meshtastic_decoder import MeshtasticDecoder
from src.decode.meshcore_decoder import MeshcoreDecoder
from src.models.packet import Packet, Protocol
from src.models.signal import SignalMetrics

_CORE_MISSING = (
    "meshpoint-core is required for packet routing. "
    "See README.md for installation instructions."
)


class PacketRouter:
    """Routes raw captured bytes to the appropriate protocol decoder.

    Requires the compiled meshpoint-core module.
    """

    def __init__(self, crypto: CryptoService):
        self._meshtastic = MeshtasticDecoder(crypto)
        self._meshcore = MeshcoreDecoder(crypto)

    @property
    def meshtastic_decoder(self) -> MeshtasticDecoder:
        return self._meshtastic

    @property
    def meshcore_decoder(self) -> MeshcoreDecoder:
        return self._meshcore

    def decode(
        self,
        raw_bytes: bytes,
        signal: Optional[SignalMetrics] = None,
        protocol_hint: Optional[Protocol] = None,
    ) -> Optional[Packet]:
        raise RuntimeError(_CORE_MISSING)
