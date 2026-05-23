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


@dataclass(frozen=True)
class ChangePasswordSuccess:
    token: str
    role: str


@dataclass(frozen=True)
class ChangePasswordFailure:
    reason: str


@dataclass(frozen=True)
class ViewerSetupSuccess:
    pass


@dataclass(frozen=True)
class ViewerSetupRejected:
    reason: str


@dataclass(frozen=True)
class LockoutConfigUpdate:
    max_attempts: int
    cooldown_minutes: int


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

    def change_password(
        self,
        *,
        subject: str,
        current_password: str,
        new_password: str,
    ) -> ChangePasswordSuccess | ChangePasswordFailure:
        """Verify current password, swap to new hash, rotate JWT secret.

        Rotating the JWT secret invalidates every other outstanding
        session in addition to the caller's cookie, so a successful
        password change forces the user (and any other tab) through
        ``/login`` on the next request. The caller receives a fresh
        token signed by the new secret so the immediate response can
        seat a working cookie.
        """
        normalized = (subject or "").strip().lower()
        if normalized not in ("admin", "viewer"):
            return ChangePasswordFailure("invalid_subject")

        stored = self._hash_for(normalized)
        if stored is None or not self._hasher.verify(current_password, stored):
            return ChangePasswordFailure("invalid_current_password")

        rejection = _validate_password(new_password)
        if rejection is not None:
            return ChangePasswordFailure(rejection)

        new_hash = self._hasher.hash(new_password)
        new_secret = JwtSessionService.generate_secret()

        if normalized == "admin":
            self._config.admin_password_hash = new_hash
        else:
            self._config.viewer_password_hash = new_hash
        self._config.jwt_secret = new_secret
        self._jwt.rotate_secret(new_secret)

        persist_payload: dict = {"jwt_secret": new_secret}
        if normalized == "admin":
            persist_payload["admin_password_hash"] = new_hash
        else:
            persist_payload["viewer_password_hash"] = new_hash
        self._persist(persist_payload)

        role = ROLE_ADMIN if normalized == "admin" else ROLE_VIEWER
        token = self._jwt.issue(subject=normalized, role=role)
        return ChangePasswordSuccess(token=token, role=role)

    def logout_all_sessions(self) -> int:
        """Bump ``session_version`` and persist; returns the new value.

        Every cookie carrying the previous ``sv`` claim fails the next
        request. The caller's own cookie is included in that sweep --
        UIs should redirect to ``/login`` immediately after a 204.
        """
        new_sv = self._jwt.bump_session_version()
        self._config.session_version = new_sv
        self._persist({"session_version": new_sv})
        return new_sv

    def update_lockout_config(
        self, max_attempts: int, cooldown_minutes: int
    ) -> LockoutConfigUpdate:
        """Apply new lockout knobs in-memory and persist.

        Validation is delegated to ``LockoutTracker.reconfigure`` so we
        get one source of truth for "what's a legal value".
        """
        self._lockout.reconfigure(max_attempts, cooldown_minutes)
        self._config.lockout_attempts = max_attempts
        self._config.lockout_cooldown_minutes = cooldown_minutes
        self._persist({
            "lockout_attempts": max_attempts,
            "lockout_cooldown_minutes": cooldown_minutes,
        })
        return LockoutConfigUpdate(
            max_attempts=max_attempts,
            cooldown_minutes=cooldown_minutes,
        )

    def update_session_lifetime(self, minutes: int) -> int:
        """Apply a new session lifetime (JWT exp) in-memory and persist.

        ``minutes`` is the number of minutes a freshly-issued login
        cookie remains valid before the user is bounced to ``/login``.
        Range is enforced by the route layer (5 min .. 30 days); we
        defensively reject non-positive values here as a final guard.

        Existing sessions keep their original ``exp`` claim -- only
        the next login (or password change) carries the new lifetime.
        Operators who want everyone re-issued under the new lifetime
        immediately can pair this with "Sign out everywhere".
        """
        if minutes <= 0:
            raise ValueError("session lifetime must be positive minutes")
        self._jwt.set_expiry_minutes(minutes)
        self._config.jwt_expiry_minutes = minutes
        self._persist({"jwt_expiry_minutes": minutes})
        return minutes

    def setup_viewer(
        self, password: str
    ) -> ViewerSetupSuccess | ViewerSetupRejected:
        """Enable the viewer role with a fresh password.

        Idempotent overwrite: calling again replaces the hash. The
        ``allow_read_only`` flag is also flipped on so the LAN UI
        surfaces viewer login instructions.
        """
        rejection = _validate_password(password)
        if rejection is not None:
            return ViewerSetupRejected(rejection)
        new_hash = self._hasher.hash(password)
        self._config.viewer_password_hash = new_hash
        self._config.allow_read_only = True
        self._persist({
            "viewer_password_hash": new_hash,
            "allow_read_only": True,
        })
        return ViewerSetupSuccess()

    def clear_viewer(self) -> None:
        """Disable the viewer role and wipe its hash."""
        self._config.viewer_password_hash = ""
        self._config.allow_read_only = False
        self._persist({
            "viewer_password_hash": "",
            "allow_read_only": False,
        })

    def viewer_enabled(self) -> bool:
        return bool(self._config.viewer_password_hash) and self._config.allow_read_only

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
