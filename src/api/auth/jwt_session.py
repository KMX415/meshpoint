"""JWT session issuance and verification.

Single responsibility: turn a (subject, role) pair into a signed
JWT and turn a JWT back into validated ``SessionClaims`` -- or
return ``None`` for any failure case (expired, bad signature, wrong
algorithm, mismatched ``session_version``, missing claim).

Two invalidation knobs are exposed by design:

- ``secret`` rotation invalidates **everything** signed by the
  previous secret (used by ``meshpoint reset-password``).
- ``session_version`` lets the operator bump a counter to drop all
  outstanding sessions without rotating the secret -- handy after
  policy changes (e.g. password rotation, role downgrade).

Algorithm is pinned to HS256: callers supply a symmetric secret and
no public key path exists, so we never want PyJWT to silently honor
``alg: none`` or RS256-with-attacker-supplied-key. ``decode`` is
called with ``algorithms=["HS256"]`` to enforce that.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

ROLE_ADMIN = "admin"
ROLE_VIEWER = "viewer"
_VALID_ROLES = frozenset({ROLE_ADMIN, ROLE_VIEWER})

_ALGORITHM = "HS256"
_SECRET_BYTES = 32


@dataclass(frozen=True)
class SessionClaims:
    """Validated claims surfaced to route-level auth dependencies."""

    subject: str
    role: str
    session_version: int


class JwtSessionService:
    """Issue and verify JWTs for the local dashboard session cookie."""

    def __init__(
        self,
        secret: str,
        expiry_minutes: int,
        session_version: int,
    ) -> None:
        if not secret:
            raise ValueError("jwt secret must not be empty")
        if expiry_minutes <= 0:
            raise ValueError("expiry_minutes must be positive")
        if session_version < 1:
            raise ValueError("session_version must be >= 1")
        self._secret = secret
        self._expiry = timedelta(minutes=expiry_minutes)
        self._session_version = session_version

    @staticmethod
    def generate_secret() -> str:
        """Return a fresh, URL-safe secret for first-run bootstrapping."""
        return secrets.token_urlsafe(_SECRET_BYTES)

    def issue(self, subject: str, role: str) -> str:
        """Sign and return a JWT for (subject, role).

        Raises ``ValueError`` for empty subject or unknown role; both
        are programming errors that should never reach runtime.
        """
        if not subject:
            raise ValueError("subject must not be empty")
        if role not in _VALID_ROLES:
            raise ValueError(f"role must be one of {sorted(_VALID_ROLES)}")
        now = datetime.now(timezone.utc)
        payload = {
            "sub": subject,
            "role": role,
            "sv": self._session_version,
            "iat": int(now.timestamp()),
            "exp": int((now + self._expiry).timestamp()),
        }
        return jwt.encode(payload, self._secret, algorithm=_ALGORITHM)

    def verify(self, token: str) -> Optional[SessionClaims]:
        """Return validated claims, or ``None`` for any failure mode."""
        if not token:
            return None
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[_ALGORITHM],
                options={"require": ["exp", "iat", "sub", "role", "sv"]},
            )
        except jwt.PyJWTError:
            return None

        subject = payload.get("sub")
        role = payload.get("role")
        token_sv = payload.get("sv")
        if not isinstance(subject, str) or not subject:
            return None
        if role not in _VALID_ROLES:
            return None
        if not isinstance(token_sv, int) or token_sv != self._session_version:
            return None
        return SessionClaims(
            subject=subject, role=role, session_version=token_sv
        )
