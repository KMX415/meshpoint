"""HTTP + WebSocket surface for the dashboard web terminal.

Three endpoints:

* ``GET  /api/terminal/commands``   -- one-click command catalog,
  returned as a list of dicts the frontend renders into buttons.
* ``GET  /api/terminal/status``     -- live count of active
  sessions and the configured cap; lets the UI surface "you have N
  shells open" without polling the WS.
* ``WS   /api/terminal/ws``         -- bidirectional PTY stream.

The WS contract is a thin JSON envelope so the same socket can
carry input bytes, output bytes, and resize events without two
separate channels:

  client -> server frames:
    { "type": "input",  "data": "<base64-encoded bytes>" }
    { "type": "resize", "rows": 40, "cols": 120 }

  server -> client frames:
    { "type": "ready",  "hostname": "...", "pid": N,
      "shell": "/bin/bash", "user": "meshpoint" }
    { "type": "output", "data": "<base64-encoded bytes>" }
    { "type": "exit",   "code": 0 }
    { "type": "error",  "message": "<reason>" }

The ``ready`` frame is emitted exactly once, immediately after the
PTY spawns, so the frontend chrome can render the live session's
hostname / pid / shell / user without an extra round trip.

The handler authenticates via the existing cookie/JWT machinery
(admin-only), spawns a new PTY session per connection, and audits
the spawn + termination through the ``AuditLogWriter``. PTY output
is forwarded by a dedicated background task that loops on
``asyncio.to_thread(session.read_nonblocking, ...)`` so we never
block the event loop on a slow read.
"""

from __future__ import annotations

import asyncio
import base64
import getpass
import json
import logging
import socket
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, status
from fastapi.websockets import WebSocketDisconnect

from src.api.audit import AuditLogWriter
from src.api.audit.dependencies import get_audit_writer
from src.api.auth.dependencies import require_admin
from src.api.auth.jwt_session import (
    ROLE_ADMIN,
    JwtSessionService,
    SessionClaims,
)
from src.api.auth.ws_guard import WS_AUTH_CLOSE_CODE, authenticate_websocket
from src.api.terminal.command_catalog import CommandCatalog
from src.api.terminal.pty_session import PtyUnavailable, PtySession
from src.api.terminal.session_manager import SessionManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/terminal", tags=["terminal"])

_session_manager: SessionManager | None = None
_command_catalog: CommandCatalog | None = None
_jwt_service: JwtSessionService | None = None
_audit_writer: AuditLogWriter | None = None


def init_routes(
    session_manager: SessionManager,
    command_catalog: CommandCatalog,
    jwt_service: JwtSessionService,
    audit_writer: AuditLogWriter,
) -> None:
    """Bind app-scope dependencies for the terminal endpoints."""
    global _session_manager, _command_catalog, _jwt_service, _audit_writer
    _session_manager = session_manager
    _command_catalog = command_catalog
    _jwt_service = jwt_service
    _audit_writer = audit_writer


def reset_routes() -> None:
    global _session_manager, _command_catalog, _jwt_service, _audit_writer
    _session_manager = None
    _command_catalog = None
    _jwt_service = None
    _audit_writer = None


def _require_initialized() -> tuple[SessionManager, CommandCatalog]:
    if _session_manager is None or _command_catalog is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="terminal not initialized",
        )
    return _session_manager, _command_catalog


@router.get("/commands")
async def list_commands(
    _claims: SessionClaims = Depends(require_admin),
    _audit: AuditLogWriter = Depends(get_audit_writer),
) -> dict:
    _manager, catalog = _require_initialized()
    return {"commands": catalog.to_payload(), "categories": catalog.categories()}


@router.get("/status")
async def terminal_status(
    _claims: SessionClaims = Depends(require_admin),
) -> dict:
    manager, _catalog = _require_initialized()
    return {
        "active_sessions": manager.session_count(),
        "max_sessions": manager.max_sessions,
    }


@router.websocket("/ws")
async def terminal_websocket(websocket: WebSocket) -> None:
    """Per-connection PTY stream.

    Authenticates the upgrade up-front; if auth fails we still
    ``accept()`` before ``close(4401)`` to mirror the server-wide
    pattern (Willard regression). Admin-only by role check after
    the cookie/JWT decode succeeds.
    """
    if _session_manager is None or _jwt_service is None:
        await websocket.accept()
        await websocket.close(code=WS_AUTH_CLOSE_CODE)
        return

    claims = authenticate_websocket(websocket, _jwt_service)
    if claims is None or claims.role != ROLE_ADMIN:
        await websocket.accept()
        await websocket.close(code=WS_AUTH_CLOSE_CODE)
        return

    await websocket.accept()
    try:
        spawn = _session_manager.spawn()
    except PtyUnavailable as exc:
        await websocket.send_json({"type": "error", "message": str(exc)})
        await websocket.close()
        return
    except RuntimeError as exc:
        await websocket.send_json({"type": "error", "message": str(exc)})
        await websocket.close()
        return

    if _audit_writer is not None:
        with _audit_writer.timed_action(
            user=claims.subject,
            action="terminal.session_spawn",
            params={"session_id": spawn.session_id, "pid": spawn.session.pid},
        ):
            pass

    try:
        await websocket.send_json({
            "type": "ready",
            "hostname": _safe_hostname(),
            "pid": spawn.session.pid,
            "shell": spawn.session.shell,
            "user": _safe_user(),
        })
    except Exception:
        logger.debug("failed to emit ready frame", exc_info=True)

    reader_task = asyncio.create_task(_pump_pty_to_ws(websocket, spawn.session))
    try:
        await _pump_ws_to_pty(websocket, spawn.session)
    finally:
        reader_task.cancel()
        try:
            await reader_task
        except (asyncio.CancelledError, Exception):
            pass
        _session_manager.destroy(spawn.session_id)
        if _audit_writer is not None:
            with _audit_writer.timed_action(
                user=claims.subject,
                action="terminal.session_close",
                params={"session_id": spawn.session_id},
            ):
                pass


async def _pump_pty_to_ws(websocket: WebSocket, session: PtySession) -> None:
    """Forward PTY output to the client until EOF / disconnect."""
    while not session.closed:
        chunk = await asyncio.to_thread(
            session.read_nonblocking, timeout_seconds=0.1
        )
        if chunk:
            try:
                await websocket.send_json({
                    "type": "output",
                    "data": base64.b64encode(chunk).decode("ascii"),
                })
            except Exception:
                return
        elif not session.is_alive():
            try:
                await websocket.send_json({"type": "exit", "code": 0})
            except Exception:
                pass
            return


async def _pump_ws_to_pty(websocket: WebSocket, session: PtySession) -> None:
    """Forward input + resize frames from the client to the PTY."""
    while True:
        try:
            raw = await websocket.receive_text()
        except WebSocketDisconnect:
            return
        frame = _safe_decode(raw)
        if frame is None:
            continue
        kind = frame.get("type")
        if kind == "input":
            payload = frame.get("data") or ""
            try:
                session.write(base64.b64decode(payload))
            except Exception:
                logger.debug("invalid input payload", exc_info=True)
        elif kind == "resize":
            rows = int(frame.get("rows") or 40)
            cols = int(frame.get("cols") or 120)
            session.resize(rows=rows, cols=cols)


def _safe_decode(raw: str) -> Optional[dict]:
    try:
        frame = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(frame, dict):
        return None
    return frame


def _safe_hostname() -> str:
    try:
        return socket.gethostname() or "meshpoint"
    except Exception:
        return "meshpoint"


def _safe_user() -> str:
    try:
        return getpass.getuser()
    except Exception:
        return "meshpoint"
