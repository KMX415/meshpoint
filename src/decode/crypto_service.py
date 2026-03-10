"""AES-CTR encryption/decryption for Meshtastic and Meshcore packets.

This is a stub module. The compiled core module (.so) overrides this
at runtime when meshpoint-core is installed.
"""

from __future__ import annotations

_CORE_MISSING = (
    "meshpoint-core is required for packet decryption. "
    "See README.md for installation instructions."
)


class CryptoService:
    """AES-CTR encryption/decryption for Meshtastic and Meshcore packets.

    Requires the compiled meshpoint-core module.
    """

    def __init__(self, default_key_b64: str = ""):
        raise RuntimeError(_CORE_MISSING)

    def add_channel_key(self, channel_name: str, key_b64: str) -> None:
        raise RuntimeError(_CORE_MISSING)

    def decrypt_meshtastic(
        self,
        encrypted_payload: bytes,
        packet_id: int,
        source_node_id: int,
    ) -> bytes | None:
        raise RuntimeError(_CORE_MISSING)

    def decrypt_meshcore(
        self,
        encrypted_payload: bytes,
        packet_id: int,
        source_node_id: int,
    ) -> bytes | None:
        raise RuntimeError(_CORE_MISSING)

    @staticmethod
    def compute_channel_hash(channel_name: str, psk: bytes) -> int:
        raise RuntimeError(_CORE_MISSING)
