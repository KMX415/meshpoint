"""Public identity endpoint: ``GET /api/identity``.

Read-only, **always allowlisted** (no auth required) so the auth
pages can render the identity strip and decide whether to redirect
to ``/setup`` before any session exists.

The handler walks an ``optional_auth`` dependency: when a valid
session cookie is present, the response carries the caller's role,
username, and the list of dashboard sections that role is allowed to
reach (``available_sections``). The sidebar uses that list to hide
sections the caller cannot use -- belt-and-braces with the per-route
``Depends(require_admin)`` server-side gating.

Strict allowlist of fields -- nothing here may leak node IDs,
positions, hardware fingerprints, or activation tokens. Anyone on
the LAN can hit ``/api/identity``, so the unauthenticated response
is deliberately small.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from src.api.auth.auth_service import AuthService
from src.api.auth.dependencies import optional_auth
from src.api.auth.jwt_session import ROLE_ADMIN, ROLE_VIEWER, SessionClaims
from src.models.device_identity import DeviceIdentity

router = APIRouter(prefix="/api", tags=["identity"])

_identity: DeviceIdentity | None = None
_auth_service: AuthService | None = None


_ADMIN_SECTIONS: tuple[str, ...] = (
    "dashboard",
    "stats",
    "messages",
    "radio",
    "terminal",
    "configuration.identity",
    "configuration.radio",
    "configuration.channels",
    "configuration.transmit",
    "configuration.mqtt",
    "configuration.gps",
    "settings",
    "settings.updates",
    "settings.auth",
    "settings.dangerous",
)

_VIEWER_SECTIONS: tuple[str, ...] = (
    "dashboard",
    "stats",
    "messages",
    "radio",
    "configuration.identity",
    "configuration.radio",
    "configuration.channels",
    "configuration.transmit",
    "configuration.mqtt",
    "configuration.gps",
)


def init_routes(identity: DeviceIdentity, auth_service: AuthService) -> None:
    """Bind device identity + auth service used by the handler."""
    global _identity, _auth_service
    _identity = identity
    _auth_service = auth_service


def reset_routes() -> None:
    """Test helper: clear module-level state between cases."""
    global _identity, _auth_service
    _identity = None
    _auth_service = None


def _sections_for(role: str) -> list[str]:
    if role == ROLE_ADMIN:
        return list(_ADMIN_SECTIONS)
    if role == ROLE_VIEWER:
        return list(_VIEWER_SECTIONS)
    return []


class IdentityResponse(BaseModel):
    device_name: str
    firmware_version: str
    setup_required: bool
    role: Optional[str] = None
    username: Optional[str] = None
    available_sections: Optional[list[str]] = None
    viewer_enabled: bool = False


@router.get("/identity", response_model=IdentityResponse)
async def get_identity(
    claims: Optional[SessionClaims] = Depends(optional_auth),
) -> IdentityResponse:
    if _identity is None or _auth_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="identity not initialized",
        )

    response_kwargs = {
        "device_name": _identity.device_name,
        "firmware_version": _identity.firmware_version,
        "setup_required": not _auth_service.is_setup_complete(),
        "viewer_enabled": _auth_service.viewer_enabled(),
    }

    if claims is not None:
        response_kwargs.update({
            "role": claims.role,
            "username": claims.subject,
            "available_sections": _sections_for(claims.role),
        })

    return IdentityResponse(**response_kwargs)
