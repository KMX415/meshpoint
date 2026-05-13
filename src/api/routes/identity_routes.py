"""Public identity endpoint: ``GET /api/identity``.

Read-only, **always allowlisted** (no auth required) so the auth
pages can render the identity strip and decide whether to redirect
to ``/setup`` before any session exists.

Strict allowlist of fields -- nothing here may leak node IDs,
positions, hardware fingerprints, or activation tokens. The auth
plan calls this out as a security boundary: anyone on the LAN can
hit ``/api/identity``, so the response must be safe for that
audience.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from src.api.auth.auth_service import AuthService
from src.models.device_identity import DeviceIdentity

router = APIRouter(prefix="/api", tags=["identity"])

_identity: DeviceIdentity | None = None
_auth_service: AuthService | None = None


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


class IdentityResponse(BaseModel):
    device_name: str
    firmware_version: str
    setup_required: bool


@router.get("/identity", response_model=IdentityResponse)
async def get_identity() -> IdentityResponse:
    if _identity is None or _auth_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="identity not initialized",
        )
    return IdentityResponse(
        device_name=_identity.device_name,
        firmware_version=_identity.firmware_version,
        setup_required=not _auth_service.is_setup_complete(),
    )
