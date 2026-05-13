"""FastAPI dependencies for the local dashboard auth contract.

Exposes three callables routes can pin via ``Depends``:

- ``require_auth``    -- reject unless a valid session is present.
- ``require_admin``   -- reject unless the session is the admin role.
- ``optional_auth``   -- attach claims if present, never reject.

Module-level state is injected once at app boot via ``init_auth``,
mirroring the pattern used by ``src.api.routes.messages.init_routes``
so route modules stay simple to test (drop in a fresh service).

Token extraction order:
1. ``Cookie: meshpoint_session=...`` (browser default; HttpOnly,
   SameSite=Lax).
2. ``Authorization: Bearer <jwt>`` (curl / non-browser clients).

Failure modes uniformly produce a 401 with a static body so we don't
leak which step rejected the request.
"""

from __future__ import annotations

from typing import NoReturn, Optional

from fastapi import Header, HTTPException, Request, status

from src.api.auth.jwt_session import (
    ROLE_ADMIN,
    JwtSessionService,
    SessionClaims,
)

SESSION_COOKIE_NAME = "meshpoint_session"
_BEARER_PREFIX = "Bearer "

_jwt_service: JwtSessionService | None = None


def init_auth(jwt_service: JwtSessionService) -> None:
    """Bind the JWT service used by all dependencies in this module."""
    global _jwt_service
    _jwt_service = jwt_service


def reset_auth() -> None:
    """Test helper: clear module-level state between cases."""
    global _jwt_service
    _jwt_service = None


def _extract_token(request: Request, authorization: Optional[str]) -> str:
    cookie_token = request.cookies.get(SESSION_COOKIE_NAME)
    if cookie_token:
        return cookie_token
    if authorization and authorization.startswith(_BEARER_PREFIX):
        return authorization[len(_BEARER_PREFIX):].strip()
    return ""


def _claims_or_none(token: str) -> Optional[SessionClaims]:
    if _jwt_service is None or not token:
        return None
    return _jwt_service.verify(token)


def _raise_unauthorized() -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _raise_forbidden() -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="admin role required",
    )


async def require_auth(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> SessionClaims:
    """Dependency: 401 unless a valid session is presented."""
    if _jwt_service is None:
        _raise_unauthorized()
    claims = _claims_or_none(_extract_token(request, authorization))
    if claims is None:
        _raise_unauthorized()
    return claims


async def require_admin(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> SessionClaims:
    """Dependency: 401 unless authed, 403 if authed but not admin."""
    claims = await require_auth(request, authorization)
    if claims.role != ROLE_ADMIN:
        _raise_forbidden()
    return claims


async def optional_auth(
    request: Request,
    authorization: Optional[str] = Header(default=None),
) -> Optional[SessionClaims]:
    """Dependency: returns claims if presented, ``None`` otherwise."""
    return _claims_or_none(_extract_token(request, authorization))
