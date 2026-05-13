"""Unit tests for ``src.api.auth.jwt_session``.

Covers happy-path issue/verify, every failure mode that must collapse
to ``None`` (bad sig, expired, missing claim, role mismatch,
``session_version`` mismatch, ``alg: none``), and constructor
guards.
"""

from __future__ import annotations

import time
import unittest
from datetime import datetime, timedelta, timezone

import jwt

from src.api.auth.jwt_session import (
    ROLE_ADMIN,
    ROLE_VIEWER,
    JwtSessionService,
    SessionClaims,
)

_SECRET = "test-secret-do-not-use-in-prod-" + "a" * 16


class TestJwtSessionService(unittest.TestCase):
    def setUp(self) -> None:
        self.service = JwtSessionService(
            secret=_SECRET, expiry_minutes=60, session_version=1
        )

    def test_issue_then_verify_admin(self) -> None:
        token = self.service.issue("admin", ROLE_ADMIN)
        claims = self.service.verify(token)
        self.assertIsInstance(claims, SessionClaims)
        assert claims is not None
        self.assertEqual(claims.subject, "admin")
        self.assertEqual(claims.role, ROLE_ADMIN)
        self.assertEqual(claims.session_version, 1)

    def test_issue_then_verify_viewer(self) -> None:
        token = self.service.issue("viewer", ROLE_VIEWER)
        claims = self.service.verify(token)
        assert claims is not None
        self.assertEqual(claims.role, ROLE_VIEWER)

    def test_verify_rejects_unknown_role(self) -> None:
        with self.assertRaises(ValueError):
            self.service.issue("admin", "superuser")

    def test_verify_rejects_empty_subject(self) -> None:
        with self.assertRaises(ValueError):
            self.service.issue("", ROLE_ADMIN)

    def test_verify_rejects_bad_signature(self) -> None:
        token = self.service.issue("admin", ROLE_ADMIN)
        other = JwtSessionService(
            secret=_SECRET[::-1], expiry_minutes=60, session_version=1
        )
        self.assertIsNone(other.verify(token))

    def test_verify_rejects_expired_token(self) -> None:
        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        payload = {
            "sub": "admin",
            "role": ROLE_ADMIN,
            "sv": 1,
            "iat": int(past.timestamp()) - 60,
            "exp": int(past.timestamp()),
        }
        token = jwt.encode(payload, _SECRET, algorithm="HS256")
        self.assertIsNone(self.service.verify(token))

    def test_verify_rejects_session_version_mismatch(self) -> None:
        token = self.service.issue("admin", ROLE_ADMIN)
        bumped = JwtSessionService(
            secret=_SECRET, expiry_minutes=60, session_version=2
        )
        self.assertIsNone(bumped.verify(token))

    def test_verify_rejects_alg_none_token(self) -> None:
        payload = {
            "sub": "admin",
            "role": ROLE_ADMIN,
            "sv": 1,
            "iat": int(time.time()),
            "exp": int(time.time()) + 60,
        }
        unsigned = jwt.encode(payload, "", algorithm="none")
        self.assertIsNone(self.service.verify(unsigned))

    def test_verify_rejects_missing_required_claim(self) -> None:
        payload = {
            "sub": "admin",
            "role": ROLE_ADMIN,
            "iat": int(time.time()),
            "exp": int(time.time()) + 60,
        }
        token = jwt.encode(payload, _SECRET, algorithm="HS256")
        self.assertIsNone(self.service.verify(token))

    def test_verify_rejects_unknown_role_in_payload(self) -> None:
        payload = {
            "sub": "mallory",
            "role": "root",
            "sv": 1,
            "iat": int(time.time()),
            "exp": int(time.time()) + 60,
        }
        token = jwt.encode(payload, _SECRET, algorithm="HS256")
        self.assertIsNone(self.service.verify(token))

    def test_verify_rejects_empty_token(self) -> None:
        self.assertIsNone(self.service.verify(""))

    def test_generate_secret_is_long_and_random(self) -> None:
        first = JwtSessionService.generate_secret()
        second = JwtSessionService.generate_secret()
        self.assertNotEqual(first, second)
        self.assertGreaterEqual(len(first), 32)

    def test_constructor_rejects_bad_inputs(self) -> None:
        with self.assertRaises(ValueError):
            JwtSessionService(secret="", expiry_minutes=60, session_version=1)
        with self.assertRaises(ValueError):
            JwtSessionService(secret=_SECRET, expiry_minutes=0, session_version=1)
        with self.assertRaises(ValueError):
            JwtSessionService(secret=_SECRET, expiry_minutes=60, session_version=0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
