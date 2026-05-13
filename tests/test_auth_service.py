"""Unit tests for ``src.api.auth.auth_service.AuthService``.

Drives each branch (setup happy/already-set/policy-rejected, login
happy/locked/wrong-password/setup-required, viewer role) through the
real PasswordHasher, JwtSessionService, and LockoutTracker -- only
the persistence callback is stubbed so we never hit disk.
"""

from __future__ import annotations

import unittest

from src.api.auth.auth_service import (
    AuthService,
    LoginFailure,
    LoginSuccess,
    SetupRejected,
    SetupSuccess,
)
from src.api.auth.jwt_session import (
    ROLE_ADMIN,
    ROLE_VIEWER,
    JwtSessionService,
)
from src.api.auth.lockout_tracker import LockoutTracker
from src.api.auth.password_hasher import PasswordHasher
from src.config import WebAuthConfig

_SECRET = "auth-service-test-secret-" + "z" * 16
_VALID_PASSWORD = "correct horse staple"
_OTHER_PASSWORD = "different password"


class _FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _build_service(
    *, web_auth: WebAuthConfig | None = None, clock: _FakeClock | None = None
) -> tuple[AuthService, list[dict], _FakeClock, WebAuthConfig]:
    cfg = web_auth or WebAuthConfig()
    persisted: list[dict] = []
    clk = clock or _FakeClock()
    service = AuthService(
        web_auth=cfg,
        hasher=PasswordHasher(rounds=4),
        lockout=LockoutTracker(max_attempts=3, cooldown_minutes=5, clock=clk),
        jwt_service=JwtSessionService(
            secret=_SECRET, expiry_minutes=60, session_version=cfg.session_version
        ),
        persist=lambda values: persisted.append(values),
    )
    return service, persisted, clk, cfg


class TestSetupFlow(unittest.TestCase):
    def test_first_run_setup_persists_hash_and_returns_token(self) -> None:
        service, persisted, _, cfg = _build_service()
        result = service.complete_setup(_VALID_PASSWORD)
        self.assertIsInstance(result, SetupSuccess)
        self.assertEqual(len(persisted), 1)
        self.assertIn("admin_password_hash", persisted[0])
        self.assertTrue(cfg.admin_password_hash.startswith("$2"))

    def test_setup_rejects_when_already_set(self) -> None:
        cfg = WebAuthConfig(admin_password_hash="$2b$04$alreadyset")
        service, persisted, _, _ = _build_service(web_auth=cfg)
        result = service.complete_setup(_VALID_PASSWORD)
        self.assertIsInstance(result, SetupRejected)
        assert isinstance(result, SetupRejected)
        self.assertEqual(result.reason, "already_set")
        self.assertEqual(persisted, [])

    def test_setup_rejects_short_password(self) -> None:
        service, persisted, _, _ = _build_service()
        result = service.complete_setup("short")
        self.assertIsInstance(result, SetupRejected)
        assert isinstance(result, SetupRejected)
        self.assertEqual(result.reason, "password_too_short")
        self.assertEqual(persisted, [])

    def test_setup_rejects_overlong_password(self) -> None:
        service, _, _, _ = _build_service()
        result = service.complete_setup("a" * 257)
        self.assertIsInstance(result, SetupRejected)


class TestLoginFlow(unittest.TestCase):
    def setUp(self) -> None:
        self.service, _, self.clock, self.cfg = _build_service()
        self.service.complete_setup(_VALID_PASSWORD)

    def test_admin_login_success_returns_token(self) -> None:
        result = self.service.login("admin", _VALID_PASSWORD)
        self.assertIsInstance(result, LoginSuccess)
        assert isinstance(result, LoginSuccess)
        self.assertEqual(result.role, ROLE_ADMIN)
        self.assertTrue(result.token)

    def test_login_is_case_insensitive_on_username(self) -> None:
        result = self.service.login("ADMIN", _VALID_PASSWORD)
        self.assertIsInstance(result, LoginSuccess)

    def test_login_wrong_password_is_invalid_credentials(self) -> None:
        result = self.service.login("admin", _OTHER_PASSWORD)
        self.assertIsInstance(result, LoginFailure)
        assert isinstance(result, LoginFailure)
        self.assertEqual(result.reason, "invalid_credentials")

    def test_login_unknown_username_collapses_to_invalid_credentials(self) -> None:
        result = self.service.login("root", _VALID_PASSWORD)
        self.assertIsInstance(result, LoginFailure)
        assert isinstance(result, LoginFailure)
        self.assertEqual(result.reason, "invalid_credentials")

    def test_login_locks_after_threshold(self) -> None:
        for _ in range(2):
            self.service.login("admin", _OTHER_PASSWORD)
        third = self.service.login("admin", _OTHER_PASSWORD)
        self.assertIsInstance(third, LoginFailure)
        assert isinstance(third, LoginFailure)
        self.assertEqual(third.reason, "invalid_credentials")
        self.assertIsNotNone(third.retry_after_seconds)

        locked = self.service.login("admin", _VALID_PASSWORD)
        self.assertIsInstance(locked, LoginFailure)
        assert isinstance(locked, LoginFailure)
        self.assertEqual(locked.reason, "locked_out")

    def test_lock_clears_after_cooldown(self) -> None:
        for _ in range(3):
            self.service.login("admin", _OTHER_PASSWORD)
        self.clock.advance(301)
        result = self.service.login("admin", _VALID_PASSWORD)
        self.assertIsInstance(result, LoginSuccess)

    def test_login_success_resets_failure_count(self) -> None:
        self.service.login("admin", _OTHER_PASSWORD)
        self.service.login("admin", _OTHER_PASSWORD)
        self.service.login("admin", _VALID_PASSWORD)
        for _ in range(2):
            result = self.service.login("admin", _OTHER_PASSWORD)
            self.assertIsInstance(result, LoginFailure)
            assert isinstance(result, LoginFailure)
            self.assertEqual(result.reason, "invalid_credentials")
        self.assertIsNone(self.service.login("admin", _VALID_PASSWORD).__dict__.get("retry_after_seconds"))


class TestViewerRole(unittest.TestCase):
    def test_viewer_login_success_when_hash_present(self) -> None:
        cfg = WebAuthConfig()
        service, _, _, _ = _build_service(web_auth=cfg)
        service.complete_setup(_VALID_PASSWORD)
        viewer_hash = PasswordHasher(rounds=4).hash("viewerpass1")
        cfg.viewer_password_hash = viewer_hash
        result = service.login("viewer", "viewerpass1")
        self.assertIsInstance(result, LoginSuccess)
        assert isinstance(result, LoginSuccess)
        self.assertEqual(result.role, ROLE_VIEWER)

    def test_viewer_login_fails_when_no_viewer_hash(self) -> None:
        service, _, _, _ = _build_service()
        service.complete_setup(_VALID_PASSWORD)
        result = service.login("viewer", "anything")
        self.assertIsInstance(result, LoginFailure)


class TestLoginPreSetup(unittest.TestCase):
    def test_login_before_setup_is_setup_required(self) -> None:
        service, _, _, _ = _build_service()
        result = service.login("admin", _VALID_PASSWORD)
        self.assertIsInstance(result, LoginFailure)
        assert isinstance(result, LoginFailure)
        self.assertEqual(result.reason, "setup_required")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
