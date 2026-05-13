"""WebSocket handshake auth gate.

Single responsibility: turn a ``WebSocket`` upgrade request into a
validated ``SessionClaims`` (or ``None``) using the same JWT service
that protects the REST API. Keeps the auth contract -- cookie
primary, ``?token=`` fallback -- in one place so the frontend has a
stable target.

Usage from ``server.py`` (or any other WS endpoint) is:

    claims = authenticate_websocket(websocket, jwt_service)
    if claims is None:
        await websocket.close(code=4401)
        return
    await ws_manager.connect(websocket)

The ``4401`` close code is a private-use frame the auth-aware
frontend client interprets as "redirect to /login".
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import WebSocket

from src.api.auth.dependencies import SESSION_COOKIE_NAME
from src.api.auth.jwt_session import JwtSessionService, SessionClaims

logger = logging.getLogger(__name__)

WS_AUTH_CLOSE_CODE = 4401


def authenticate_websocket(
    websocket: WebSocket, jwt_service: Optional[JwtSessionService]
) -> Optional[SessionClaims]:
    """Return validated session claims for a WS upgrade or ``None``."""
    if jwt_service is None:
        return None
    token = _extract_token(websocket)
    if not token:
        return None
    claims = jwt_service.verify(token)
    if claims is None:
        logger.info(
            "WS auth rejected (token prefix=%s)", _safe_prefix(token)
        )
    return claims


def _extract_token(websocket: WebSocket) -> str:
    cookie = websocket.cookies.get(SESSION_COOKIE_NAME)
    if cookie:
        return cookie
    query_token = websocket.query_params.get("token")
    if query_token:
        return query_token
    return ""


def _safe_prefix(token: str, length: int = 12) -> str:
    """Trim a token to a length we're comfortable putting in logs."""
    return (token[:length] + "...") if len(token) > length else "***"
