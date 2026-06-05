"""Tests for Meshpoint PKI keypair storage."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from src.identity.keypair import KeypairStore, MeshpointKeypair


class TestMeshpointKeypair(unittest.TestCase):
    def test_generate_round_trip(self):
        kp = MeshpointKeypair.generate()
        self.assertEqual(len(kp.private_key), 32)
        self.assertEqual(len(kp.public_key), 32)
        restored = MeshpointKeypair.from_private_bytes(kp.private_key)
        self.assertEqual(restored.public_key, kp.public_key)

    def test_load_or_create_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keys.yaml"
            store = KeypairStore(path)
            first = store.load_or_create()
            second = store.load_or_create()
            self.assertEqual(first.private_key, second.private_key)
            self.assertTrue(path.is_file())
            mode = path.stat().st_mode & 0o777
            if os.name != "nt":
                self.assertEqual(mode, 0o600)


if __name__ == "__main__":
    unittest.main()
