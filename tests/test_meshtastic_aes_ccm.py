"""Tests for Meshtastic firmware-compatible AES-CCM."""

from __future__ import annotations

import unittest

from src.decode.meshtastic_aes_ccm import MeshtasticAesCcmEngine


class TestMeshtasticAesCcm(unittest.TestCase):
    def test_round_trip_empty_aad(self):
        key = bytes(range(32))
        nonce = bytes(range(13))
        plaintext = b"mesh participant dm"
        engine = MeshtasticAesCcmEngine(key)
        crypt, auth = engine.encrypt(nonce, 8, plaintext)
        recovered = engine.decrypt(nonce, 8, crypt, auth)
        self.assertEqual(recovered, plaintext)

    def test_tampered_auth_fails(self):
        key = b"\x01" * 32
        nonce = b"\x02" * 13
        plaintext = b"hello"
        engine = MeshtasticAesCcmEngine(key)
        crypt, auth = engine.encrypt(nonce, 8, plaintext)
        bad_auth = bytes([auth[0] ^ 0xFF]) + auth[1:]
        self.assertIsNone(engine.decrypt(nonce, 8, crypt, bad_auth))

    def test_short_ciphertext_rejected(self):
        key = b"\x03" * 32
        nonce = b"\x04" * 13
        engine = MeshtasticAesCcmEngine(key)
        crypt, auth = engine.encrypt(nonce, 8, b"x")
        self.assertIsNone(engine.decrypt(nonce, 8, crypt[:-1], auth))


if __name__ == "__main__":
    unittest.main()
