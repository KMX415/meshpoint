"""Auth-related configuration endpoints.

Three admin-only endpoints, all prefixed ``/api/config/``:

* ``GET  /auth_settings``         -- live snapshot of lockout +
  session-lifetime values, used to prime the Settings -> Auth forms
  without leaking anything to ``/api/identity`` (which is public).
* ``PUT  /auth_lockout``          -- failed-login lockout knobs
  (max attempts, cooldown minutes).
* ``PUT  /auth_session_lifetime`` -- how long a fresh login stays
  valid before the user gets bounced to ``/login``. Configurable
  from 5 minutes to 30 days; only newly-issued sessions inherit the
  new value (existing cookies keep their original ``exp``).

Distinct from ``auth_routes`` because these are *configuration*
changes (round-trips to ``local.yaml``) rather than session
lifecycle events (login, logout, password change).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.api.audit import AuditLogWriter
from src.api.audit.dependencies import get_audit_writer
from src.api.auth.auth_service import AuthService
from src.api.auth.dependencies import require_admin
from src.api.auth.jwt_session import SessionClaims

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])

_auth_service: AuthService | None = None


def init_routes(auth_service: AuthService) -> None:
    global _auth_service
    _auth_service = auth_service


def reset_routes() -> None:
    global _auth_service
    _auth_service = None


def _service() -> AuthService:
    if _auth_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="auth not initialized",
        )
    return _auth_service


class AuthLockoutRequest(BaseModel):
    lockout_attempts: int = Field(..., ge=1, le=100)
    lockout_cooldown_minutes: int = Field(..., ge=1, le=1440)


# Session lifetime range:
#   5 minutes  -- minimum useful value for kiosk-mode setups
#   43_200     -- 30 days; longer than that and the cookie is
#                 effectively "stay logged in forever", which we
#                 surface as a separate UX choice rather than a
#                 numeric input
_SESSION_LIFETIME_MIN_MINUTES = 5
_SESSION_LIFETIME_MAX_MINUTES = 30 * 24 * 60


class AuthSessionLifetimeRequest(BaseModel):
    session_lifetime_minutes: int = Field(
        ...,
        ge=_SESSION_LIFETIME_MIN_MINUTES,
        le=_SESSION_LIFETIME_MAX_MINUTES,
    )


@router.get("/auth_settings")
async def get_auth_settings(
    _claims: SessionClaims = Depends(require_admin),
) -> dict:
    """Return current lockout + session-lifetime values (admin only).

    Kept off ``/api/identity`` so anonymous LAN clients can't enumerate
    operational policy. The Settings -> Auth panel hits this on mount
    to prime the forms with live values instead of guessing defaults.
    """
    cfg = _service().config
    return {
        "lockout_attempts": cfg.lockout_attempts,
        "lockout_cooldown_minutes": cfg.lockout_cooldown_minutes,
        "session_lifetime_minutes": cfg.jwt_expiry_minutes,
        "session_lifetime_min_minutes": _SESSION_LIFETIME_MIN_MINUTES,
        "session_lifetime_max_minutes": _SESSION_LIFETIME_MAX_MINUTES,
    }


@router.put("/auth_lockout")
async def update_auth_lockout(
    payload: AuthLockoutRequest,
    claims: SessionClaims = Depends(require_admin),
    audit: AuditLogWriter = Depends(get_audit_writer),
) -> dict:
    """Update failed-login lockout configuration (admin only)."""
    with audit.timed_action(
        user=claims.subject,
        action="config.auth_lockout_update",
        params={
            "lockout_attempts": payload.lockout_attempts,
            "lockout_cooldown_minutes": payload.lockout_cooldown_minutes,
        },
    ):
        result = _service().update_lockout_config(
            max_attempts=payload.lockout_attempts,
            cooldown_minutes=payload.lockout_cooldown_minutes,
        )
    return {
        "lockout_attempts": result.max_attempts,
        "lockout_cooldown_minutes": result.cooldown_minutes,
    }


@router.put("/auth_session_lifetime")
async def update_session_lifetime(
    payload: AuthSessionLifetimeRequest,
    claims: SessionClaims = Depends(require_admin),
    audit: AuditLogWriter = Depends(get_audit_writer),
) -> dict:
    """Update the JWT session lifetime applied to new logins.

    The new value takes effect on the next ``/api/auth/login`` (or
    password-change) call; sessions issued with the old lifetime keep
    their original ``exp`` claim until natural expiry. Operators who
    want a hard refresh can pair this with "Sign out everywhere".
    """
    with audit.timed_action(
        user=claims.subject,
        action="config.auth_session_lifetime_update",
        params={
            "session_lifetime_minutes": payload.session_lifetime_minutes,
        },
    ):
        applied = _service().update_session_lifetime(
            payload.session_lifetime_minutes,
        )
    return {"session_lifetime_minutes": applied}
