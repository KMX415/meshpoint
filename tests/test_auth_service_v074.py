"""Coverage for the v0.7.4 auth-service additions.

Five new operations land for v0.7.4:

* ``change_password`` -- rotate admin or viewer password; rotates the
  JWT secret as a side effect so every other browser is kicked.
* ``logout_all_sessions`` -- bump ``session_version`` to invalidate
  every outstanding cookie without nuking the secret.
* ``update_lockout_config`` -- set ``lockout_attempts`` and
  ``lockout_cooldown_minutes`` from the dashboard.
* ``setup_viewer`` / ``clear_viewer`` -- enable or disable the
  read-only viewer role.

Tests use ``rounds=4`` for ``PasswordHasher`` so the suite stays fast.
"""

from __future__ import annotations

import unittest

from src.api.auth.auth_service import (
    AuthService,
    ChangePasswordFailure,
    ChangePasswordSuccess,
    ViewerSetupRejected,
    ViewerSetupSuccess,
)
from src.api.auth.jwt_session import JwtSessionService
from src.api.auth.lockout_tracker import LockoutTracker
from src.api.auth.password_hasher import PasswordHasher
from src.config import WebAuthConfig

_SECRET = "v074-tests-jwt-secret-" + "a" * 32


class _PersistSpy:
    def __init__(self) -> None:
        self.payloads: list[dict] = []

    def __call__(self, values: dict) -> None:
        self.payloads.append(values)


def _fresh_admin_service():
    cfg = WebAuthConfig(jwt_secret=_SECRET)
    spy = _PersistSpy()
    hasher = PasswordHasher(rounds=4)
    cfg.admin_password_hash = hasher.hash("originalpw")
    jwt = JwtSessionService(_SECRET, expiry_minutes=60, session_version=1)
    svc = AuthService(
        web_auth=cfg,
        hasher=hasher,
        lockout=LockoutTracker(max_attempts=3, cooldown_minutes=2),
        jwt_service=jwt,
        persist=spy,
    )
    return svc, cfg, jwt, spy


class TestChangePassword(unittest.TestCase):
    def test_success_rotates_secret_and_returns_new_token(self) -> None:
        svc, cfg, jwt, spy = _fresh_admin_service()
        before_secret = cfg.jwt_secret

        result = svc.change_password(
            subject="admin",
            current_password="originalpw",
            new_password="newpassword1",
        )

        self.assertIsInstance(result, ChangePasswordSuccess)
        self.assertEqual(result.role, "admin")
        self.assertNotEqual(cfg.jwt_secret, before_secret)
        self.assertIsNotNone(jwt.verify(result.token))

    def test_old_token_invalidated_after_change(self) -> None:
        svc, _cfg, jwt, _spy = _fresh_admin_service()
        old_token = jwt.issue("admin", "admin")
        self.assertIsNotNone(jwt.verify(old_token))

        svc.change_password(
            subject="admin",
            current_password="originalpw",
            new_password="newpassword1",
        )

        self.assertIsNone(jwt.verify(old_token))

    def test_persist_writes_admin_hash_and_secret(self) -> None:
        svc, _cfg, _jwt, spy = _fresh_admin_service()
        svc.change_password(
            subject="admin",
            current_password="originalpw",
            new_password="newpassword1",
        )
        last = spy.payloads[-1]
        self.assertIn("admin_password_hash", last)
        self.assertIn("jwt_secret", last)
        self.assertNotEqual(last["admin_password_hash"], "")

    def test_wrong_current_password_returns_failure(self) -> None:
        svc, _cfg, _jwt, spy = _fresh_admin_service()
        result = svc.change_password(
            subject="admin",
            current_password="bogus",
            new_password="newpassword1",
        )
        self.assertIsInstance(result, ChangePasswordFailure)
        self.assertEqual(result.reason, "invalid_current_password")
        self.assertEqual(spy.payloads, [])

    def test_short_new_password_rejected(self) -> None:
        svc, *_ = _fresh_admin_service()
        result = svc.change_password(
            subject="admin",
            current_password="originalpw",
            new_password="short",
        )
        self.assertIsInstance(result, ChangePasswordFailure)
        self.assertEqual(result.reason, "password_too_short")

    def test_invalid_subject_rejected(self) -> None:
        svc, *_ = _fresh_admin_service()
        result = svc.change_password(
            subject="root",
            current_password="originalpw",
            new_password="newpassword1",
        )
        self.assertIsInstance(result, ChangePasswordFailure)
        self.assertEqual(result.reason, "invalid_subject")


class TestLogoutAllSessions(unittest.TestCase):
    def test_bumps_session_version_and_persists(self) -> None:
        svc, cfg, jwt, spy = _fresh_admin_service()
        before = cfg.session_version
        new_sv = svc.logout_all_sessions()
        self.assertEqual(new_sv, before + 1)
        self.assertEqual(cfg.session_version, new_sv)
        self.assertEqual(jwt.session_version, new_sv)
        self.assertEqual(spy.payloads[-1], {"session_version": new_sv})

    def test_old_token_invalidated_after_bump(self) -> None:
        svc, _cfg, jwt, _spy = _fresh_admin_service()
        token = jwt.issue("admin", "admin")
        self.assertIsNotNone(jwt.verify(token))
        svc.logout_all_sessions()
        self.assertIsNone(jwt.verify(token))


class TestUpdateLockoutConfig(unittest.TestCase):
    def test_persists_and_reconfigures_tracker(self) -> None:
        svc, cfg, _jwt, spy = _fresh_admin_service()
        result = svc.update_lockout_config(max_attempts=10, cooldown_minutes=15)
        self.assertEqual(result.max_attempts, 10)
        self.assertEqual(result.cooldown_minutes, 15)
        self.assertEqual(cfg.lockout_attempts, 10)
        self.assertEqual(cfg.lockout_cooldown_minutes, 15)
        self.assertEqual(svc._lockout.max_attempts, 10)
        self.assertEqual(svc._lockout.cooldown_minutes, 15)
        self.assertEqual(spy.payloads[-1], {
            "lockout_attempts": 10,
            "lockout_cooldown_minutes": 15,
        })

    def test_invalid_zero_attempts_raises(self) -> None:
        svc, *_ = _fresh_admin_service()
        with self.assertRaises(ValueError):
            svc.update_lockout_config(max_attempts=0, cooldown_minutes=5)


class TestUpdateSessionLifetime(unittest.TestCase):
    def test_persists_and_updates_jwt_service(self) -> None:
        svc, cfg, jwt, spy = _fresh_admin_service()
        result = svc.update_session_lifetime(720)
        self.assertEqual(result, 720)
        self.assertEqual(cfg.jwt_expiry_minutes, 720)
        self.assertEqual(jwt.expiry_minutes, 720)
        self.assertEqual(spy.payloads[-1], {"jwt_expiry_minutes": 720})

    def test_zero_minutes_rejected(self) -> None:
        svc, *_ = _fresh_admin_service()
        with self.assertRaises(ValueError):
            svc.update_session_lifetime(0)

    def test_negative_minutes_rejected(self) -> None:
        svc, *_ = _fresh_admin_service()
        with self.assertRaises(ValueError):
            svc.update_session_lifetime(-5)

    def test_jwt_issued_after_update_carries_new_lifetime(self) -> None:
        import jwt as _jwt

        svc, _cfg, jwt_service, _spy = _fresh_admin_service()
        svc.update_session_lifetime(1440)
        token = jwt_service.issue(subject="admin", role="admin")
        decoded = _jwt.decode(
            token, _SECRET, algorithms=["HS256"],
            options={"require": ["exp", "iat"]},
        )
        ttl_seconds = decoded["exp"] - decoded["iat"]
        # Allow ±5s clock slack; delta should be ~24 hours.
        self.assertGreater(ttl_seconds, 1440 * 60 - 5)
        self.assertLess(ttl_seconds, 1440 * 60 + 5)


class TestViewerLifecycle(unittest.TestCase):
    def test_setup_viewer_writes_hash_and_enables_flag(self) -> None:
        svc, cfg, _jwt, spy = _fresh_admin_service()
        result = svc.setup_viewer("viewerpassword1")
        self.assertIsInstance(result, ViewerSetupSuccess)
        self.assertNotEqual(cfg.viewer_password_hash, "")
        self.assertTrue(cfg.allow_read_only)
        self.assertTrue(svc.viewer_enabled())
        self.assertIn("viewer_password_hash", spy.payloads[-1])
        self.assertEqual(spy.payloads[-1]["allow_read_only"], True)

    def test_setup_viewer_rejects_short_password(self) -> None:
        svc, *_ = _fresh_admin_service()
        result = svc.setup_viewer("short")
        self.assertIsInstance(result, ViewerSetupRejected)
        self.assertEqual(result.reason, "password_too_short")

    def test_clear_viewer_wipes_hash_and_disables_flag(self) -> None:
        svc, cfg, _jwt, _spy = _fresh_admin_service()
        svc.setup_viewer("viewerpassword1")
        svc.clear_viewer()
        self.assertEqual(cfg.viewer_password_hash, "")
        self.assertFalse(cfg.allow_read_only)
        self.assertFalse(svc.viewer_enabled())


if __name__ == "__main__":
    unittest.main()
