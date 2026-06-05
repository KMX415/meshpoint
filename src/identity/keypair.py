"""Persistent X25519 keypair for Meshtastic PKI."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey

logger = logging.getLogger(__name__)

PRIVATE_KEY_BYTES = 32
PUBLIC_KEY_BYTES = 32


@dataclass(frozen=True)
class MeshpointKeypair:
    """Meshtastic-compatible Curve25519 keypair."""

    private_key: bytes
    public_key: bytes

    @classmethod
    def generate(cls) -> MeshpointKeypair:
        private = X25519PrivateKey.generate()
        public = private.public_key()
        priv_bytes = private.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
        pub_bytes = public.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return cls(private_key=priv_bytes, public_key=pub_bytes)

    @classmethod
    def from_private_bytes(cls, private_key: bytes) -> MeshpointKeypair:
        if len(private_key) != PRIVATE_KEY_BYTES:
            raise ValueError("private key must be 32 bytes")
        private = X25519PrivateKey.from_private_bytes(private_key)
        public = private.public_key()
        pub_bytes = public.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return cls(private_key=bytes(private_key), public_key=pub_bytes)


class KeypairStore:
    """Load or create the Meshpoint PKI key file."""

    def __init__(self, path: Path):
        self._path = path

    @property
    def path(self) -> Path:
        return self._path

    def load_or_create(self) -> MeshpointKeypair:
        if self._path.is_file():
            return self._load()
        keypair = MeshpointKeypair.generate()
        self._save(keypair)
        logger.info("Generated new Meshtastic PKI keypair at %s", self._path)
        return keypair

    def _load(self) -> MeshpointKeypair:
        raw = yaml.safe_load(self._path.read_text(encoding="utf-8")) or {}
        priv_hex = raw.get("private_key_hex", "")
        if not priv_hex or len(priv_hex) != PRIVATE_KEY_BYTES * 2:
            raise ValueError(f"invalid key file: {self._path}")
        private_key = bytes.fromhex(priv_hex)
        keypair = MeshpointKeypair.from_private_bytes(private_key)
        if raw.get("public_key_hex") != keypair.public_key.hex():
            logger.warning(
                "public_key_hex mismatch in %s; using derived public key",
                self._path,
            )
        return keypair

    def _save(self, keypair: MeshpointKeypair) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "private_key_hex": keypair.private_key.hex(),
            "public_key_hex": keypair.public_key.hex(),
        }
        temp_path = self._path.with_suffix(".tmp")
        temp_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
        os.replace(temp_path, self._path)
        try:
            os.chmod(self._path, 0o600)
        except OSError:
            logger.debug("Could not chmod key file to 0600", exc_info=True)


def resolve_keypair_path(database_path: str) -> Path:
    """Return ``data/keys.yaml`` beside the SQLite database."""
    db_dir = Path(database_path).resolve().parent
    return db_dir / "keys.yaml"


def resolve_keypair_path_from_env() -> Path | None:
    """Optional override via ``MESHPOINT_KEYS_PATH``."""
    override = os.environ.get("MESHPOINT_KEYS_PATH", "").strip()
    if override:
        return Path(override)
    return None
