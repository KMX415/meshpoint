"""HTTP shell for the local-dashboard auth flow.

Three endpoints sit on this router:

- ``POST /api/auth/setup``  -- one-shot first-run admin password set.
- ``POST /api/auth/login``  -- credential validation + cookie issue.
- ``POST /api/auth/logout`` -- cookie clear (JWT is stateless on the
  server -- ``session_version`` rotation is the global revocation).

The handlers stay thin: they delegate every decision to
``AuthService`` and translate ``LoginFailure`` / ``SetupRejected``
return values into HTTP responses. All cookie hardening (HttpOnly,
SameSite=Lax, Secure-when-HTTPS) is applied here in one place so the
contract is auditable.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from src.api.auth.auth_service import (
    AuthService,
    LoginFailure,
    LoginSuccess,
    SetupRejected,
    SetupSuccess,
)
from src.api.auth.dependencies import SESSION_COOKIE_NAME

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_auth_service: AuthService | None = None


def init_routes(auth_service: AuthService) -> None:
    """Bind the AuthService used by every handler in this module."""
    global _auth_service
    _auth_service = auth_service


def reset_routes() -> None:
    """Test helper: clear module-level state between cases."""
    global _auth_service
    _auth_service = None


class SetupRequest(BaseModel):
    password: str = Field(..., min_length=1, max_length=512)


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=512)


def _service() -> AuthService:
    if _auth_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="auth not initialized",
        )
    return _auth_service


def _set_session_cookie(
    request: Request, response: Response, token: str
) -> None:
    """Apply hardened cookie attributes for the session JWT."""
    is_https = request.url.scheme == "https"
    expiry_minutes = _service().config.jwt_expiry_minutes
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=expiry_minutes * 60,
        httponly=True,
        secure=is_https,
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
    )


def _reject_setup(rejection: SetupRejected) -> HTTPException:
    if rejection.reason == "already_set":
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="already_set",
        )
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=rejection.reason,
    )


def _reject_login(failure: LoginFailure) -> HTTPException:
    if failure.reason == "locked_out":
        headers = (
            {"Retry-After": str(failure.retry_after_seconds)}
            if failure.retry_after_seconds is not None
            else None
        )
        return HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="locked_out",
            headers=headers,
        )
    if failure.reason == "setup_required":
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="setup_required",
        )
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid_credentials",
    )


@router.post("/setup")
async def setup_password(
    payload: SetupRequest, request: Request, response: Response
) -> dict:
    result = _service().complete_setup(payload.password)
    if isinstance(result, SetupSuccess):
        _set_session_cookie(request, response, result.token)
        logger.info("admin password set via /api/auth/setup")
        return {"role": "admin"}
    raise _reject_setup(result)


@router.post("/login")
async def login(
    payload: LoginRequest, request: Request, response: Response
) -> dict:
    result = _service().login(payload.username, payload.password)
    if isinstance(result, LoginSuccess):
        _set_session_cookie(request, response, result.token)
        logger.info("user logged in (role=%s)", result.role)
        return {"role": result.role}
    raise _reject_login(result)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> None:
    _clear_session_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
