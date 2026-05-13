"""Unit tests for ``src.cli.reset_password_command.run_reset_password``.

Drives the command with stub prompt callables and captured persister
so we can assert (a) the new bcrypt hash is written, (b) the JWT
secret is rotated, and (c) ``session_version`` is bumped -- all in
one persisted call so a partial failure can't strand the device.
"""

from __future__ import annotations

import io
import unittest

from src.api.auth.password_hasher import PasswordHasher
from src.cli.reset_password_command import _CliWriter, run_reset_password
from src.config import AppConfig, WebAuthConfig


class _FakeConfigLoader:
    def __init__(self, web_auth: WebAuthConfig) -> None:
        self._web_auth = web_auth

    def __call__(self) -> AppConfig:
        cfg = AppConfig()
        cfg.web_auth = self._web_auth
        return cfg


class _CapturingPersister:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, section: str, values: dict) -> None:
        self.calls.append((section, values))


def _writer() -> _CliWriter:
    return _CliWriter(io.StringIO())


def _stub_prompt(value: str):
    def _ask(_label: str) -> str:
        return value
    return _ask


class TestResetPasswordCommand(unittest.TestCase):
    def setUp(self) -> None:
        self.web_auth = WebAuthConfig(
            admin_password_hash="$2b$04$old",
            jwt_secret="old-secret-do-not-reuse",
            session_version=1,
        )
        self.persister = _CapturingPersister()

    def _run(self, password: str, confirm: str) -> int:
        return run_reset_password(
            prompt_password=_stub_prompt(password),
            confirm_password=_stub_prompt(confirm),
            writer=_writer(),
            config_loader=_FakeConfigLoader(self.web_auth),
            persister=self.persister,
        )

    def test_success_writes_new_hash_and_rotates_secret(self) -> None:
        exit_code = self._run("brand-new-pass-1", "brand-new-pass-1")
        self.assertEqual(exit_code, 0)
        self.assertEqual(len(self.persister.calls), 1)
        section, values = self.persister.calls[0]
        self.assertEqual(section, "web_auth")
        self.assertIn("admin_password_hash", values)
        self.assertIn("jwt_secret", values)
        self.assertIn("session_version", values)
        self.assertNotEqual(values["jwt_secret"], "old-secret-do-not-reuse")
        self.assertGreaterEqual(values["session_version"], 2)

    def test_new_hash_is_verifiable(self) -> None:
        self._run("verifiable-pass", "verifiable-pass")
        new_hash = self.persister.calls[0][1]["admin_password_hash"]
        self.assertTrue(PasswordHasher(rounds=4).verify("verifiable-pass", new_hash))

    def test_mismatched_passwords_abort_without_persist(self) -> None:
        exit_code = self._run("password-one", "password-two")
        self.assertEqual(exit_code, 1)
        self.assertEqual(self.persister.calls, [])

    def test_short_password_aborts_without_persist(self) -> None:
        exit_code = self._run("short", "short")
        self.assertEqual(exit_code, 1)
        self.assertEqual(self.persister.calls, [])

    def test_session_version_bumps_from_default(self) -> None:
        self.web_auth.session_version = 7
        self._run("rotate-pass-1", "rotate-pass-1")
        values = self.persister.calls[0][1]
        self.assertEqual(values["session_version"], 8)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
