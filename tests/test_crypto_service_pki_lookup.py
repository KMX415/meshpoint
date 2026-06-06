"""Tests for CryptoService PKI peer key lookup."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.decode.crypto_service import CryptoService
from src.identity.keypair import MeshpointKeypair


class TestCryptoServicePkiLookup(unittest.TestCase):
    def setUp(self):
        self.crypto = CryptoService()
        self.peer = MeshpointKeypair.generate()
        self.peer_id = 0x7D8B98A9

    def test_lookup_falls_back_to_sqlite(self):
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            with sqlite3.connect(db_path) as conn:
                conn.execute(
                    """
                    CREATE TABLE nodes (
                        node_id TEXT PRIMARY KEY,
                        public_key TEXT
                    )
                    """
                )
                conn.execute(
                    "INSERT INTO nodes (node_id, public_key) VALUES (?, ?)",
                    (f"{self.peer_id:08x}", self.peer.public_key.hex()),
                )
                conn.commit()

            self.crypto.set_node_db_path(db_path)
            loaded = self.crypto.lookup_public_key(self.peer_id)
            self.assertEqual(loaded, self.peer.public_key)
            self.assertEqual(
                self.crypto.lookup_public_key(self.peer_id),
                self.peer.public_key,
            )
        finally:
            self.crypto.set_node_db_path("")
            try:
                Path(db_path).unlink(missing_ok=True)
            except PermissionError:
                pass


if __name__ == "__main__":
    unittest.main()
