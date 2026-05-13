"""Regression coverage for AuthSubsystem assembly.

The historical bug this guards: the original implementation persisted
the auto-generated jwt_secret to local.yaml at service start. On a
fresh-SD install that ran install.sh + systemd before the user ran
``meshpoint setup``, this created a stub local.yaml just containing
``web_auth.jwt_secret``, which then made the setup wizard print
"Existing config/local.yaml found" on what was actually a clean
install. The fix moves the disk write into AuthService.complete_setup
so a true fresh install only writes local.yaml when the user has
configured something.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from src.api.auth.auth_bootstrap import build_auth_subsystem
from src.config import AppConfig, WebAuthConfig


class _CountingPatcher:
    """Records how many times save_section_to_yaml is called and with what."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, section: str, values: dict) -> None:
        self.calls.append((section, values))


class TestAuthBootstrapFreshInstall(unittest.TestCase):
    def test_jwt_secret_generated_in_memory_only_no_disk_write(self) -> None:
        """A fresh install must not pollute local.yaml from auth boot."""
        cfg = AppConfig()
        self.assertEqual(cfg.web_auth.jwt_secret, "")
        spy = _CountingPatcher()
        with patch("src.api.auth.auth_bootstrap.save_section_to_yaml", spy):
            subsystem = build_auth_subsystem(cfg)

        self.assertNotEqual(cfg.web_auth.jwt_secret, "")
        self.assertEqual(
            spy.calls,
            [],
            "auth bootstrap must not write local.yaml on first run; "
            "secret persists when /setup completes",
        )
        self.assertEqual(
            subsystem.jwt_service._secret,
            cfg.web_auth.jwt_secret,
            "JwtSessionService must use the same secret that was set "
            "on the WebAuthConfig",
        )

    def test_existing_jwt_secret_is_left_alone(self) -> None:
        """An upgrade with a populated local.yaml is a no-op."""
        cfg = AppConfig()
        cfg.web_auth = WebAuthConfig(
            jwt_secret="already-on-disk-from-prior-setup",
            admin_password_hash="$2b$04$exists",
        )
        spy = _CountingPatcher()
        with patch("src.api.auth.auth_bootstrap.save_section_to_yaml", spy):
            build_auth_subsystem(cfg)

        self.assertEqual(
            cfg.web_auth.jwt_secret, "already-on-disk-from-prior-setup"
        )
        self.assertEqual(spy.calls, [])


class TestCompleteSetupPersistsJwtSecret(unittest.TestCase):
    def test_complete_setup_persists_jwt_secret_alongside_password_hash(
        self,
    ) -> None:
        """The first /setup call is what creates local.yaml."""
        from src.api.auth.auth_service import AuthService, SetupSuccess
        from src.api.auth.jwt_session import JwtSessionService
        from src.api.auth.lockout_tracker import LockoutTracker
        from src.api.auth.password_hasher import PasswordHasher

        cfg = WebAuthConfig(jwt_secret="bootstrap-generated-in-memory")
        persisted: list[dict] = []
        service = AuthService(
            web_auth=cfg,
            hasher=PasswordHasher(rounds=4),
            lockout=LockoutTracker(max_attempts=5, cooldown_minutes=5),
            jwt_service=JwtSessionService(
                secret="bootstrap-generated-in-memory",
                expiry_minutes=60,
                session_version=1,
            ),
            persist=lambda values: persisted.append(values),
        )

        result = service.complete_setup("hunter22-strong")
        self.assertIsInstance(result, SetupSuccess)
        self.assertEqual(len(persisted), 1)
        self.assertIn("admin_password_hash", persisted[0])
        self.assertIn("jwt_secret", persisted[0])
        self.assertEqual(
            persisted[0]["jwt_secret"], "bootstrap-generated-in-memory"
        )


if __name__ == "__main__":
    unittest.main()
