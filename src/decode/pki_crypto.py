"""Meshtastic 2.5+ PKI crypto (X25519 + AES-CCM)."""

from __future__ import annotations

import hashlib
import secrets
import struct

from src.decode.meshtastic_aes_ccm import MeshtasticAesCcmEngine

PKC_OVERHEAD = 12
PKC_MIC_LEN = 8
PKC_NONCE_LEN = 13


def build_pki_nonce(
    from_node_id: int, packet_id: int, extra_nonce: int = 0
) -> bytes:
    """Build the 13-byte nonce buffer used by Meshtastic CryptoEngine."""
    nonce = bytearray(13)
    struct.pack_into("<Q", nonce, 0, packet_id & 0xFFFFFFFFFFFFFFFF)
    struct.pack_into("<I", nonce, 8, from_node_id & 0xFFFFFFFF)
    if extra_nonce:
        struct.pack_into("<I", nonce, 4, extra_nonce & 0xFFFFFFFF)
    return bytes(nonce)


def derive_shared_key(private_key: bytes, remote_public_key: bytes) -> bytes:
    """X25519 ECDH followed by SHA-256, matching Meshtastic firmware."""
    from cryptography.hazmat.primitives.asymmetric.x25519 import (
        X25519PrivateKey,
        X25519PublicKey,
    )

    if len(private_key) != 32 or len(remote_public_key) != 32:
        raise ValueError("PKI keys must be 32 bytes")
    priv = X25519PrivateKey.from_private_bytes(private_key)
    pub = X25519PublicKey.from_public_bytes(remote_public_key)
    shared = priv.exchange(pub)
    return hashlib.sha256(shared).digest()


def encrypt_pki_payload(
    plaintext: bytes,
    *,
    private_key: bytes,
    remote_public_key: bytes,
    from_node_id: int,
    packet_id: int,
) -> bytes | None:
    """Encrypt a direct-message payload with AES-CCM."""
    try:
        shared_key = derive_shared_key(private_key, remote_public_key)
        extra_nonce = secrets.randbits(32)
        nonce = build_pki_nonce(from_node_id, packet_id, extra_nonce)
        engine = MeshtasticAesCcmEngine(shared_key)
        ciphertext, mic = engine.encrypt(nonce, PKC_MIC_LEN, plaintext)
        return ciphertext + mic + struct.pack("<I", extra_nonce)
    except Exception:
        return None


def decrypt_pki_payload(
    encrypted: bytes,
    *,
    private_key: bytes,
    remote_public_key: bytes,
    from_node_id: int,
    packet_id: int,
) -> bytes | None:
    """Decrypt a PKI direct-message payload."""
    if len(encrypted) <= PKC_OVERHEAD:
        return None
    try:
        body_len = len(encrypted) - PKC_OVERHEAD
        ciphertext = encrypted[:body_len]
        auth = encrypted[body_len:]
        extra_nonce = struct.unpack("<I", auth[8:12])[0]
        shared_key = derive_shared_key(private_key, remote_public_key)
        nonce = build_pki_nonce(from_node_id, packet_id, extra_nonce)
        engine = MeshtasticAesCcmEngine(shared_key)
        return engine.decrypt(nonce, PKC_MIC_LEN, ciphertext, auth[:PKC_MIC_LEN])
    except Exception:
        return None
