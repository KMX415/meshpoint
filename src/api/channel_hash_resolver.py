"""Meshtastic channel_hash → dashboard channel index for inbound routing."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

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
        """Rebuild the hash map from live crypto keys and config names."""
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
            if index >= len(all_keys):
                break
            ch_hash = crypto.compute_channel_hash(ch_name, all_keys[index])
            self._hash_to_index[ch_hash] = index

        logger.info("Channel hash map: %s", self._hash_to_index)

    def lookup(self, channel_hash: int) -> int:
        """Return dashboard channel index for a packet header hash."""
        mapped = self._hash_to_index.get(channel_hash)
        if mapped is not None:
            return mapped
        if channel_hash not in self._warned_hashes:
            self._warned_hashes.add(channel_hash)
            logger.warning(
                "Unmapped Meshtastic channel_hash=0x%02x; "
                "routing broadcast to channel 0",
                channel_hash,
            )
        return 0

    @property
    def mapping(self) -> dict[int, int]:
        """Read-only view of the current hash → index map (tests)."""
        return dict(self._hash_to_index)
