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

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field

from src.api.audit import AuditLogWriter
from src.api.audit.dependencies import get_audit_writer
from src.api.auth.auth_service import (
    AuthService,
    ChangePasswordFailure,
    LoginFailure,
    LoginSuccess,
    SetupRejected,
    SetupSuccess,
    ViewerSetupRejected,
)
from src.api.auth.dependencies import (
    SESSION_COOKIE_NAME,
    require_admin,
    require_auth,
)
from src.api.auth.jwt_session import SessionClaims

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


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=512)
    new_password: str = Field(..., min_length=1, max_length=512)


class ViewerSetupRequest(BaseModel):
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


@router.post("/change_password")
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    claims: SessionClaims = Depends(require_auth),
    audit: AuditLogWriter = Depends(get_audit_writer),
) -> dict:
    """Rotate the caller's password (admin or viewer).

    Persists the new bcrypt hash and rotates ``jwt_secret`` so every
    other browser session is dropped. The caller's cookie is
    re-issued so the immediate response reseats a working session.
    Audit log records the action; never the password values.
    """
    with audit.timed_action(
        user=claims.subject,
        action="auth.change_password",
        params={"subject": claims.subject},
    ) as ctx:
        result = _service().change_password(
            subject=claims.subject,
            current_password=payload.current_password,
            new_password=payload.new_password,
        )
        if isinstance(result, ChangePasswordFailure):
            ctx.set_result("error")
            ctx.params["reason"] = result.reason
            raise _reject_change_password(result)
        _set_session_cookie(request, response, result.token)
        ctx.params["role"] = result.role
        return {"role": result.role}


@router.post("/logout_all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    response: Response,
    claims: SessionClaims = Depends(require_admin),
    audit: AuditLogWriter = Depends(get_audit_writer),
) -> None:
    """Invalidate every outstanding session (admin only).

    Bumps ``session_version`` server-side so every existing JWT fails
    verification on next request. The caller's cookie is dropped here;
    the frontend redirects to ``/login`` on the resulting 401.
    """
    with audit.timed_action(
        user=claims.subject,
        action="auth.logout_all",
    ) as ctx:
        new_sv = _service().logout_all_sessions()
        ctx.params["session_version"] = new_sv
    _clear_session_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT


@router.post("/setup_viewer", status_code=status.HTTP_200_OK)
async def setup_viewer(
    payload: ViewerSetupRequest,
    claims: SessionClaims = Depends(require_admin),
    audit: AuditLogWriter = Depends(get_audit_writer),
) -> dict:
    """Enable the viewer role with a fresh password (admin only)."""
    with audit.timed_action(
        user=claims.subject, action="auth.setup_viewer",
    ) as ctx:
        result = _service().setup_viewer(payload.password)
        if isinstance(result, ViewerSetupRejected):
            ctx.set_result("error")
            ctx.params["reason"] = result.reason
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.reason,
            )
    return {"viewer_enabled": True}


@router.post("/clear_viewer", status_code=status.HTTP_204_NO_CONTENT)
async def clear_viewer(
    response: Response,
    claims: SessionClaims = Depends(require_admin),
    audit: AuditLogWriter = Depends(get_audit_writer),
) -> None:
    """Disable the viewer role (admin only)."""
    with audit.timed_action(user=claims.subject, action="auth.clear_viewer"):
        _service().clear_viewer()
    response.status_code = status.HTTP_204_NO_CONTENT


def _reject_change_password(
    failure: ChangePasswordFailure,
) -> HTTPException:
    if failure.reason == "invalid_current_password":
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_current_password",
        )
    if failure.reason in ("password_too_short", "password_too_long"):
        return HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=failure.reason,
        )
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=failure.reason,
    )
