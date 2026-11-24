"""Resolves Meshtastic channel hashes to human-readable channel names.

The Meshtastic firmware computes a channel hash by XOR-ing all channel name
bytes with all expanded encryption key bytes (xorHash()). This module
pre-computes hash-to-name mappings for standard presets using the default PSK
and for any user-configured channel keys.

Used by MqttPublisher and MeshtasticMqttFormatter to build correct MQTT
topics (e.g. msh/US/2/e/MediumFast/!gateway instead of msh/US/2/e/ch31/!gateway).
Also reusable for upstream privacy controls (channel allowlist filtering).
"""

from __future__ import annotations

import base64
import logging
from typing import Optional

from src.models.packet import Protocol

logger = logging.getLogger(__name__)

_DEFAULT_PSK = bytes([
    0xD4, 0xF1, 0xBB, 0x3A, 0x20, 0x29, 0x07, 0x59,
    0xF0, 0xBC, 0xFF, 0xAB, 0xCF, 0x4E, 0x69, 0x01,
])

STANDARD_PRESETS = [
    "LongFast",
    "LongTurbo",
    "LongSlow",
    "LongModerate",
    "MediumFast",
    "MediumSlow",
    "ShortFast",
    "ShortSlow",
    "ShortTurbo",
]


def _expand_key(raw_key: bytes) -> bytes:
    """Expand short PSK to full AES key length (mirrors firmware logic)."""
    if len(raw_key) == 0:
        return b"\x00" * 16
    if len(raw_key) in (16, 32):
        return raw_key
    if len(raw_key) == 1:
        index = raw_key[0]
        if index == 0:
            return b"\x00" * 16
        key = bytearray(_DEFAULT_PSK)
        key[-1] = (key[-1] + index - 1) & 0xFF
        return bytes(key)
    return (raw_key + b"\x00" * 16)[:16]


def _xor_hash(channel_name: str, expanded_key: bytes) -> int:
    """Compute channel hash matching Meshtastic firmware xorHash()."""
    h = 0
    for b in channel_name.encode():
        h ^= b
    for b in expanded_key:
        h ^= b
    return h & 0xFF


class ChannelResolver:
    """Maps channel_hash values to channel names for MQTT topic construction.

    Pre-seeds mappings for standard Meshtastic presets using the
    default PSK. Accepts additional user-configured channel keys to extend
    the lookup table for private/custom channels.
    """

    def __init__(
        self,
        channel_keys: Optional[dict[str, str]] = None,
        default_key_b64: str = "AQ==",
    ):
        self._hash_to_name: dict[int, str] = {}
        self._build_default_presets(default_key_b64)
        if channel_keys:
            self._build_user_channels(channel_keys)

    def resolve(self, channel_hash: int, protocol: Protocol) -> str:
        """Return channel name for a given hash and protocol.

        MeshCore packets always resolve to "MeshCore".
        Meshtastic packets look up the hash, falling back to "ch{hash}".
        """
        if protocol == Protocol.MESHCORE:
            return "MeshCore"
        if channel_hash == 0:
            return "LongFast"
        return self._hash_to_name.get(channel_hash, f"ch{channel_hash}")

    def is_known(self, channel_hash: int) -> bool:
        return channel_hash == 0 or channel_hash in self._hash_to_name

    def _build_default_presets(self, default_key_b64: str) -> None:
        expanded_key = _expand_key(base64.b64decode(default_key_b64))
        for name in STANDARD_PRESETS:
            h = _xor_hash(name, expanded_key)
            self._hash_to_name[h] = name

    def _build_user_channels(self, channel_keys: dict[str, str]) -> None:
        """Add hash mappings for user-configured channel keys."""
        for name, key_b64 in channel_keys.items():
            try:
                expanded = _expand_key(base64.b64decode(key_b64))
                h = _xor_hash(name, expanded)
                self._hash_to_name[h] = name
                logger.debug(
                    "Channel '%s' registered with hash %d", name, h
                )
            except Exception:
                logger.warning(
                    "Failed to compute hash for channel '%s', skipping", name
                )
