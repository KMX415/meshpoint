"""Auth orchestration: setup, login, logout flows.

Single responsibility: glue ``PasswordHasher``, ``JwtSessionService``,
and ``LockoutTracker`` into the three operations the dashboard needs
without ever touching FastAPI itself. Routes call ``AuthService`` and
translate its return values into HTTP responses; CLI tooling
(``meshpoint reset-password``) calls the same service.

Persistence is injected as a ``ConfigPersister`` callable so tests
never touch the filesystem and so production callers can route the
write through ``save_section_to_yaml`` (which already preserves
unrelated sections).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from src.api.auth.jwt_session import (
    ROLE_ADMIN,
    ROLE_VIEWER,
    JwtSessionService,
)
from src.api.auth.lockout_tracker import LockoutTracker
from src.api.auth.password_hasher import PasswordHasher
from src.config import WebAuthConfig

_MIN_PASSWORD_LENGTH = 8
_MAX_PASSWORD_LENGTH = 256


ConfigPersister = Callable[[dict], None]


@dataclass(frozen=True)
class LoginSuccess:
    token: str
    role: str


@dataclass(frozen=True)
class LoginFailure:
    reason: str
    retry_after_seconds: Optional[int] = None


@dataclass(frozen=True)
class SetupSuccess:
    token: str


@dataclass(frozen=True)
class SetupRejected:
    reason: str


class AuthService:
    """Stateless orchestrator over the three auth primitives.

    A single instance is created at app startup and shared across
    requests. All mutable state (failed-login counters, the rolling
    JWT secret) lives in the injected collaborators -- the service
    itself only routes calls.
    """

    def __init__(
        self,
        web_auth: WebAuthConfig,
        hasher: PasswordHasher,
        lockout: LockoutTracker,
        jwt_service: JwtSessionService,
        persist: ConfigPersister,
    ) -> None:
        self._config = web_auth
        self._hasher = hasher
        self._lockout = lockout
        self._jwt = jwt_service
        self._persist = persist

    @property
    def config(self) -> WebAuthConfig:
        return self._config

    def is_setup_complete(self) -> bool:
        return bool(self._config.admin_password_hash)

    def complete_setup(self, password: str) -> SetupSuccess | SetupRejected:
        """Hash the supplied password and persist it as the admin hash.

        Also writes ``jwt_secret`` so a fresh install picks up its
        in-memory bootstrap secret on the same disk write -- avoids
        polluting ``local.yaml`` before the user has actually
        configured anything (see ``auth_bootstrap``).

        Returns ``SetupRejected`` if setup has already happened (LAN
        attacker prevention) or if the password fails the policy check.
        """
        if self.is_setup_complete():
            return SetupRejected("already_set")
        rejection = _validate_password(password)
        if rejection is not None:
            return SetupRejected(rejection)

        hashed = self._hasher.hash(password)
        self._config.admin_password_hash = hashed
        self._persist({
            "admin_password_hash": hashed,
            "jwt_secret": self._config.jwt_secret,
        })
        token = self._jwt.issue(subject="admin", role=ROLE_ADMIN)
        return SetupSuccess(token=token)

    def login(self, username: str, password: str) -> LoginSuccess | LoginFailure:
        """Validate credentials and return a session token.

        ``username`` is restricted to ``admin`` / ``viewer``. Every
        other value short-circuits to ``invalid_credentials`` so we
        never expose which usernames exist.
        """
        if not self.is_setup_complete():
            return LoginFailure("setup_required")

        normalized = (username or "").strip().lower()
        cooldown = self._lockout.remaining_seconds(normalized)
        if cooldown is not None:
            return LoginFailure("locked_out", retry_after_seconds=cooldown)

        stored_hash = self._hash_for(normalized)
        if stored_hash is None or not self._hasher.verify(password, stored_hash):
            triggered = self._lockout.register_failure(normalized)
            return LoginFailure(
                "invalid_credentials", retry_after_seconds=triggered
            )

        self._lockout.register_success(normalized)
        role = ROLE_ADMIN if normalized == "admin" else ROLE_VIEWER
        token = self._jwt.issue(subject=normalized, role=role)
        return LoginSuccess(token=token, role=role)

    def _hash_for(self, normalized_username: str) -> Optional[str]:
        if normalized_username == "admin":
            return self._config.admin_password_hash or None
        if normalized_username == "viewer":
            return self._config.viewer_password_hash or None
        return None


def _validate_password(password: str) -> Optional[str]:
    if not isinstance(password, str):
        return "invalid_password"
    if len(password) < _MIN_PASSWORD_LENGTH:
        return "password_too_short"
    if len(password) > _MAX_PASSWORD_LENGTH:
        return "password_too_long"
    return None
