"""Interactive ``meshpoint reset-password`` recovery command.

Last-resort recovery path for the local dashboard: a host-level
operator (SSH'd in as ``pi``/``meshpoint``) prompts for a fresh
admin password, the new bcrypt hash is written to ``local.yaml``,
the JWT secret is rotated, and ``session_version`` is bumped so any
session minted before the reset is invalidated immediately.

The command depends only on ``WebAuthConfig`` + ``PasswordHasher``
+ ``JwtSessionService.generate_secret`` -- it deliberately does not
import the FastAPI app or the running pipeline so it works against
a stopped service.
"""

from __future__ import annotations

import getpass
import sys
from typing import Callable

from src.api.auth.jwt_session import JwtSessionService
from src.api.auth.password_hasher import PasswordHasher
from src.config import load_config, save_section_to_yaml

_MIN_PASSWORD_LENGTH = 8


PromptFn = Callable[[str], str]


class _CliWriter:
    """Tiny wrapper around print so tests can capture output."""

    def __init__(self, sink=None) -> None:
        self._sink = sink or sys.stdout

    def writeln(self, text: str = "") -> None:
        print(text, file=self._sink)


def run_reset_password(
    *,
    prompt_password: PromptFn = getpass.getpass,
    confirm_password: PromptFn = getpass.getpass,
    writer: _CliWriter | None = None,
    config_loader: Callable = load_config,
    persister: Callable[[str, dict], None] = save_section_to_yaml,
) -> int:
    """Run the interactive reset-password flow.

    Returns a process-style exit code (``0`` on success, non-zero on
    user cancel / mismatch). All I/O collaborators are injectable so
    the test suite can drive it without spawning a TTY.
    """
    out = writer or _CliWriter()
    out.writeln()
    out.writeln("  Meshpoint password reset")
    out.writeln("  Sets a new admin password and invalidates any open sessions.")
    out.writeln()

    try:
        password = prompt_password("  New admin password: ")
        confirm = confirm_password("  Confirm new password: ")
    except (KeyboardInterrupt, EOFError):
        out.writeln()
        out.writeln("  Aborted.")
        return 130

    if password != confirm:
        out.writeln()
        out.writeln("  Passwords did not match. No changes written.")
        return 1
    if len(password) < _MIN_PASSWORD_LENGTH:
        out.writeln()
        out.writeln(
            f"  Password must be at least {_MIN_PASSWORD_LENGTH} characters."
        )
        return 1

    config = config_loader()
    new_hash = PasswordHasher().hash(password)
    new_secret = JwtSessionService.generate_secret()
    new_version = max(1, config.web_auth.session_version) + 1

    persister(
        "web_auth",
        {
            "admin_password_hash": new_hash,
            "jwt_secret": new_secret,
            "session_version": new_version,
        },
    )

    out.writeln()
    out.writeln(
        "  Password reset complete. Open http://<meshpoint-ip>/ and sign in."
    )
    return 0
