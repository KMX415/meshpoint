"""Tests for Meshtastic PKI crypto helpers."""

from __future__ import annotations

import unittest

from src.decode.pki_crypto import (
    PKC_OVERHEAD,
    build_pki_nonce,
    decrypt_pki_payload,
    encrypt_pki_payload,
)
from src.identity.keypair import MeshpointKeypair


class TestPkiCrypto(unittest.TestCase):
    def setUp(self):
        self.alice = MeshpointKeypair.generate()
        self.bob = MeshpointKeypair.generate()
        self.packet_id = 0x12345678
        self.alice_id = 0xAABBCCDD
        self.plaintext = b"hello mesh participant"

    def test_nonce_layout(self):
        nonce = build_pki_nonce(self.alice_id, self.packet_id, 0x01020304)
        self.assertEqual(len(nonce), 13)

    def test_encrypt_decrypt_round_trip(self):
        encrypted = encrypt_pki_payload(
            self.plaintext,
            private_key=self.alice.private_key,
            remote_public_key=self.bob.public_key,
            from_node_id=self.alice_id,
            packet_id=self.packet_id,
        )
        self.assertIsNotNone(encrypted)
        assert encrypted is not None
        self.assertGreater(len(encrypted), len(self.plaintext))
        self.assertGreaterEqual(len(encrypted), PKC_OVERHEAD)

        decrypted = decrypt_pki_payload(
            encrypted,
            private_key=self.bob.private_key,
            remote_public_key=self.alice.public_key,
            from_node_id=self.alice_id,
            packet_id=self.packet_id,
        )
        self.assertEqual(decrypted, self.plaintext)

    def test_pki_with_fixed_extra_nonce(self):
        """Deterministic path used by Meshtastic firmware extraNonce field."""
        from unittest.mock import patch

        fixed_extra = 0xDEADBEEF
        with patch("src.decode.pki_crypto.secrets.randbits", return_value=fixed_extra):
            encrypted = encrypt_pki_payload(
                self.plaintext,
                private_key=self.alice.private_key,
                remote_public_key=self.bob.public_key,
                from_node_id=self.alice_id,
                packet_id=self.packet_id,
            )
        self.assertIsNotNone(encrypted)
        assert encrypted is not None
        decrypted = decrypt_pki_payload(
            encrypted,
            private_key=self.bob.private_key,
            remote_public_key=self.alice.public_key,
            from_node_id=self.alice_id,
            packet_id=self.packet_id,
        )
        self.assertEqual(decrypted, self.plaintext)


if __name__ == "__main__":
    unittest.main()
