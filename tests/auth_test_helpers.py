"""Shared auth overrides for FastAPI TestClient route suites."""

from __future__ import annotations

from fastapi import FastAPI

from src.api.auth.dependencies import require_admin, require_auth
from src.api.auth.jwt_session import SessionClaims


def override_as_admin(app: FastAPI) -> None:
    """Satisfy require_auth / require_admin without a real JWT service."""

    async def _admin() -> SessionClaims:
        return SessionClaims(subject="admin", role="admin", session_version=1)

    app.dependency_overrides[require_admin] = _admin
    app.dependency_overrides[require_auth] = _admin


def override_as_viewer(app: FastAPI) -> None:
    """Auth as viewer; admin-only deps still return 403."""
    from fastapi import HTTPException, status

    async def _viewer() -> SessionClaims:
        return SessionClaims(subject="viewer", role="viewer", session_version=1)

    async def _forbid_admin() -> SessionClaims:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="admin role required",
        )

    app.dependency_overrides[require_auth] = _viewer
    app.dependency_overrides[require_admin] = _forbid_admin
