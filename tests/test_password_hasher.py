"""Unit tests for ``src.api.auth.password_hasher``.

Uses bcrypt rounds=4 throughout to keep the suite fast (each
hash/verify is < 5 ms vs ~250 ms at the production cost factor).
"""

from __future__ import annotations

import unittest

from src.api.auth.password_hasher import PasswordHasher


class TestPasswordHasher(unittest.TestCase):
    def setUp(self) -> None:
        self.hasher = PasswordHasher(rounds=4)

    def test_hash_then_verify_roundtrip(self) -> None:
        digest = self.hasher.hash("correct horse battery staple")
        self.assertTrue(digest.startswith("$2"))
        self.assertTrue(self.hasher.verify("correct horse battery staple", digest))

    def test_verify_rejects_wrong_password(self) -> None:
        digest = self.hasher.hash("hunter2")
        self.assertFalse(self.hasher.verify("hunter3", digest))

    def test_verify_returns_false_for_empty_stored_hash(self) -> None:
        self.assertFalse(self.hasher.verify("anything", ""))

    def test_verify_returns_false_for_empty_candidate(self) -> None:
        digest = self.hasher.hash("hunter2")
        self.assertFalse(self.hasher.verify("", digest))

    def test_verify_returns_false_for_malformed_hash(self) -> None:
        self.assertFalse(self.hasher.verify("hunter2", "not-a-bcrypt-hash"))

    def test_hash_rejects_empty_password(self) -> None:
        with self.assertRaises(ValueError):
            self.hasher.hash("")

    def test_hash_rejects_non_string_password(self) -> None:
        with self.assertRaises(TypeError):
            self.hasher.hash(b"bytes-not-allowed")  # type: ignore[arg-type]

    def test_two_hashes_of_same_password_differ(self) -> None:
        first = self.hasher.hash("repeat")
        second = self.hasher.hash("repeat")
        self.assertNotEqual(first, second)
        self.assertTrue(self.hasher.verify("repeat", first))
        self.assertTrue(self.hasher.verify("repeat", second))

    def test_unicode_password_supported(self) -> None:
        password = "p\u00e1ssw\u00f8rd-\U0001f680"
        digest = self.hasher.hash(password)
        self.assertTrue(self.hasher.verify(password, digest))
        self.assertFalse(self.hasher.verify(password + "x", digest))

    def test_rounds_out_of_range_rejected(self) -> None:
        with self.assertRaises(ValueError):
            PasswordHasher(rounds=2)
        with self.assertRaises(ValueError):
            PasswordHasher(rounds=20)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
