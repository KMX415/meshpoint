from __future__ import annotations

import base64
import logging
import struct

from Crypto.Cipher import AES  # nosec B413 -- pycryptodome, not deprecated pyCrypto

from src.decode.pki_crypto import (
    PKC_OVERHEAD,
    decrypt_pki_payload,
    encrypt_pki_payload,
)

logger = logging.getLogger(__name__)

MESHTASTIC_DEFAULT_KEY_B64 = "AQ=="
NONCE_SIZE = 16

MESHTASTIC_DEFAULT_PSK = bytes([
    0xD4, 0xF1, 0xBB, 0x3A, 0x20, 0x29, 0x07, 0x59,
    0xF0, 0xBC, 0xFF, 0xAB, 0xCF, 0x4E, 0x69, 0x01,
])


class CryptoService:
    """AES-CTR encryption/decryption for Meshtastic and Meshcore packets."""

    def __init__(self, default_key_b64: str = MESHTASTIC_DEFAULT_KEY_B64):
        self._keys: dict[str, bytes] = {}
        self._private_key: bytes | None = None
        self._public_key: bytes | None = None
        self._public_keys: dict[int, bytes] = {}
        self._node_db_path: str | None = None
        if default_key_b64:
            self._default_key = self._expand_key(
                base64.b64decode(default_key_b64)
            )
        else:
            self._default_key = None

    def add_channel_key(self, channel_name: str, key_b64: str) -> None:
        raw = base64.b64decode(key_b64)
        self._keys[channel_name] = self._expand_key(raw)

    def clear_channel_keys(self) -> None:
        """Drop all non-default channel keys."""
        self._keys.clear()

    def set_keypair(self, private_key: bytes, public_key: bytes) -> None:
        """Install the Meshpoint Meshtastic PKI keypair."""
        self._private_key = private_key
        self._public_key = public_key

    @property
    def public_key(self) -> bytes | None:
        return self._public_key

    def has_pki(self) -> bool:
        return self._private_key is not None and self._public_key is not None

    def set_node_db_path(self, db_path: str) -> None:
        """Optional SQLite path for on-demand peer public_key lookup."""
        self._node_db_path = db_path

    def register_public_key(self, node_id: int, public_key: bytes) -> None:
        if public_key and len(public_key) == 32:
            self._public_keys[node_id] = public_key

    def lookup_public_key(self, node_id: int) -> bytes | None:
        cached = self._public_keys.get(node_id)
        if cached is not None:
            return cached
        loaded = self._load_public_key_from_db(node_id)
        if loaded is not None:
            self._public_keys[node_id] = loaded
        return loaded

    def refresh_public_key_from_db(self, node_id: int) -> bytes | None:
        """Drop cached peer key and reload from SQLite if configured."""
        self._public_keys.pop(node_id, None)
        return self.lookup_public_key(node_id)

    def _load_public_key_from_db(self, node_id: int) -> bytes | None:
        if not self._node_db_path:
            return None
        import sqlite3

        node_hex = f"{node_id:08x}"
        try:
            with sqlite3.connect(self._node_db_path) as conn:
                row = conn.execute(
                    "SELECT public_key FROM nodes "
                    "WHERE lower(node_id) = lower(?) "
                    "AND public_key IS NOT NULL AND public_key != ''",
                    (node_hex,),
                ).fetchone()
            if not row or not row[0]:
                return None
            key = bytes.fromhex(row[0])
            if len(key) != 32:
                logger.warning(
                    "Ignoring invalid public_key length for node %s", node_hex
                )
                return None
            return key
        except (ValueError, sqlite3.Error):
            logger.debug(
                "Failed to load public_key for %s from DB", node_hex, exc_info=True
            )
            return None

    def decrypt_meshtastic_pki(
        self,
        encrypted_payload: bytes,
        packet_id: int,
        sender_node_id: int,
        sender_public_key: bytes,
    ) -> bytes | None:
        if self._private_key is None:
            return None
        return decrypt_pki_payload(
            encrypted_payload,
            private_key=self._private_key,
            remote_public_key=sender_public_key,
            from_node_id=sender_node_id,
            packet_id=packet_id,
        )

    def encrypt_meshtastic_pki(
        self,
        plaintext: bytes,
        packet_id: int,
        source_node_id: int,
        recipient_public_key: bytes,
    ) -> bytes | None:
        if self._private_key is None:
            return None
        return encrypt_pki_payload(
            plaintext,
            private_key=self._private_key,
            remote_public_key=recipient_public_key,
            from_node_id=source_node_id,
            packet_id=packet_id,
        )

    @staticmethod
    def is_pki_packet(
        channel_hash: int,
        dest_id: int,
        our_node_id: int | None,
        payload_len: int,
    ) -> bool:
        return (
            channel_hash == 0
            and our_node_id is not None
            and dest_id == our_node_id
            and dest_id != 0xFFFFFFFF
            and payload_len > PKC_OVERHEAD
        )

    def get_all_keys(self) -> list[bytes]:
        """Return all available keys, default first then channel keys."""
        keys: list[bytes] = []
        if self._default_key:
            keys.append(self._default_key)
        keys.extend(self._keys.values())
        return keys

    def decrypt_meshtastic(
        self,
        encrypted_payload: bytes,
        packet_id: int,
        source_node_id: int,
        key: bytes | None = None,
    ) -> bytes | None:
        """Decrypt a Meshtastic packet payload using AES-CTR.

        If key is provided, use it directly. Otherwise fall back to
        the default key. The nonce is built from packet_id and
        source_node_id, matching the firmware's initNonce().
        """
        use_key = key if key is not None else self._default_key
        if use_key is None:
            logger.debug("No decryption key available")
            return None

        nonce = self._build_meshtastic_nonce(packet_id, source_node_id)
        return self._aes_ctr_decrypt(use_key, nonce, encrypted_payload)

    def encrypt_meshtastic(
        self,
        plaintext: bytes,
        packet_id: int,
        source_node_id: int,
        key: bytes | None = None,
    ) -> bytes | None:
        """Encrypt a Meshtastic payload using AES-CTR.

        Symmetric to decrypt_meshtastic: same nonce, same key expansion.
        Returns ciphertext or None if no key is available.
        """
        use_key = key if key is not None else self._default_key
        if use_key is None:
            logger.debug("No encryption key available")
            return None

        nonce = self._build_meshtastic_nonce(packet_id, source_node_id)
        try:
            cipher = AES.new(
                use_key, AES.MODE_CTR, nonce=b"", initial_value=nonce
            )
            return cipher.encrypt(plaintext)
        except Exception:
            logger.debug("AES-CTR encryption failed", exc_info=True)
            return None

    def decrypt_meshcore(
        self,
        encrypted_payload: bytes,
        packet_id: int,
        source_node_id: int,
    ) -> bytes | None:
        """Decrypt a Meshcore packet payload (AES-256-CTR)."""
        key = self._default_key
        if key is None:
            return None

        nonce = self._build_meshcore_nonce(packet_id, source_node_id)
        return self._aes_ctr_decrypt(key, nonce, encrypted_payload)

    @staticmethod
    def _expand_key(raw_key: bytes) -> bytes:
        """Expand short keys for AES.

        Meshtastic key handling (mirrors firmware Channels::getKey):
        - 0 bytes  -> encryption disabled (return zeros)
        - 1 byte   -> well-known key index; firmware uses defaultpsk
                       with last byte bumped by (index - 1)
        - 16 bytes -> AES-128, use as-is
        - 32 bytes -> AES-256, use as-is
        - other    -> zero-pad to 16 bytes
        """
        if len(raw_key) == 0:
            return b"\x00" * 16
        if len(raw_key) in (16, 32):
            return raw_key
        if len(raw_key) == 1:
            index = raw_key[0]
            if index == 0:
                return b"\x00" * 16
            key = bytearray(MESHTASTIC_DEFAULT_PSK)
            key[-1] = (key[-1] + index - 1) & 0xFF
            return bytes(key)
        return (raw_key + b"\x00" * 16)[:16]

    @staticmethod
    def _build_meshtastic_nonce(
        packet_id: int, source_node_id: int
    ) -> bytes:
        """Build the 16-byte CTR nonce matching Meshtastic firmware.

        Layout: packet_id (4B LE) + 0 (4B) + source_node_id (4B LE) + 0 (4B)
        """
        nonce = struct.pack("<I", packet_id)
        nonce += b"\x00" * 4
        nonce += struct.pack("<I", source_node_id)
        nonce += b"\x00" * 4
        return nonce

    @staticmethod
    def _build_meshcore_nonce(
        packet_id: int, source_node_id: int
    ) -> bytes:
        """Build the 16-byte CTR nonce for Meshcore decryption.

        Layout: packet_id (4B LE) + 0 (4B) + source_node_id (4B LE) + 0 (4B)
        """
        nonce = struct.pack("<I", packet_id)
        nonce += b"\x00" * 4
        nonce += struct.pack("<I", source_node_id)
        nonce += b"\x00" * 4
        return nonce

    @staticmethod
    def _aes_ctr_decrypt(
        key: bytes, nonce: bytes, ciphertext: bytes
    ) -> bytes | None:
        try:
            cipher = AES.new(key, AES.MODE_CTR, nonce=b"", initial_value=nonce)
            return cipher.decrypt(ciphertext)
        except Exception:
            logger.debug("AES-CTR decryption failed", exc_info=True)
            return None

    @staticmethod
    def compute_channel_hash(channel_name: str, expanded_key: bytes) -> int:
        """Compute the Meshtastic channel hash matching firmware xorHash().

        The firmware XORs all name bytes, then XORs all expanded key
        bytes, then combines the two. Callers must pass the key after
        expansion (via _expand_key), not raw base64 bytes.
        """
        h = 0
        for b in channel_name.encode():
            h ^= b
        for b in expanded_key:
            h ^= b
        return h & 0xFF
