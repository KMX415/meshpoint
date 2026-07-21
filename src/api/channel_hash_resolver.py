"""Meshtastic channel_hash → dashboard channel index for inbound routing."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from src.decode.crypto_service import CryptoService

logger = logging.getLogger(__name__)


class ChannelHashResolver:
    """Maps Meshtastic header channel_hash bytes to conversation channel index.

    Channel 0 is the primary channel (default PSK + ``primary_channel_name``).
    Additional configured keys are indexed 1..N in ``channel_keys`` order.
    """

    def __init__(self) -> None:
        self._hash_to_index: dict[int, int] = {}
        self._warned_hashes: set[int] = set()

    def rebuild(
        self,
        crypto: CryptoService,
        primary_channel_name: str,
        channel_keys: dict[str, str],
    ) -> None:
        """Rebuild the hash map from live crypto keys and config names.

        Looks up each secondary channel's key by name via
        ``crypto.get_channel_key`` (not by position in ``get_all_keys``),
        so config/crypto ordering drift cannot mis-map hashes
        (javastraat/meshpoint abc2f56).
        """
        self._hash_to_index.clear()
        self._warned_hashes.clear()

        primary = (primary_channel_name or "LongFast").strip() or "LongFast"
        all_keys = crypto.get_all_keys()
        if not all_keys:
            logger.warning("Channel hash map empty: no crypto keys loaded")
            return

        primary_hash = crypto.compute_channel_hash(primary, all_keys[0])
        self._hash_to_index[primary_hash] = 0

        for index, ch_name in enumerate(channel_keys.keys(), start=1):
            key = crypto.get_channel_key(ch_name)
            if key is None:
                continue
            ch_hash = crypto.compute_channel_hash(ch_name, key)
            self._hash_to_index[ch_hash] = index

        logger.info("Channel hash map: %s", self._hash_to_index)

    def lookup(self, channel_hash: int) -> Optional[int]:
        """Return dashboard channel index, or None if unmapped.

        Never defaults to channel 0. Callers must route None to a distinct
        visible bucket (javastraat/meshpoint 73f692d).
        """
        mapped = self._hash_to_index.get(channel_hash)
        if mapped is not None:
            return mapped
        if channel_hash not in self._warned_hashes:
            self._warned_hashes.add(channel_hash)
            logger.warning(
                "Unmapped Meshtastic channel_hash=0x%02x; routing to a "
                "distinct unmapped bucket instead of blending into channel 0",
                channel_hash,
            )
        return None

    @property
    def mapping(self) -> dict[int, int]:
        """Read-only view of the current hash → index map (tests)."""
        return dict(self._hash_to_index)
