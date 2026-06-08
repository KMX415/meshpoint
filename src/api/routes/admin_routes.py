"""Remote Meshtastic ADMIN config read routes (PR 15)."""
from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.admin.pending_store import DEBOUNCE_SECONDS, REQUEST_TIMEOUT_SECONDS
from src.admin.reader import AdminConfigError, AdminConfigReader
from src.api.audit import AuditLogWriter
from src.api.audit.dependencies import get_audit_writer
from src.api.auth.dependencies import require_admin
from src.api.auth.jwt_session import SessionClaims

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])

_reader: AdminConfigReader | None = None


def init_routes(*, reader: AdminConfigReader | None) -> None:
    global _reader
    _reader = reader


def reset_routes() -> None:
    global _reader
    _reader = None


class ConfigRequestBody(BaseModel):
    section: Literal[
        "device",
        "owner",
        "lora",
        "position",
        "power",
        "network",
        "display",
        "bluetooth",
        "security",
    ] = Field(default="device")


@router.get("/remote-config/status")
async def remote_config_status():
    """Whether remote ADMIN config read is configured (no secrets)."""
    if _reader is None:
        return {
            "available": False,
            "debounce_seconds": DEBOUNCE_SECONDS,
            "timeout_seconds": REQUEST_TIMEOUT_SECONDS,
        }
    return {
        "available": _reader.available,
        "debounce_seconds": DEBOUNCE_SECONDS,
        "timeout_seconds": REQUEST_TIMEOUT_SECONDS,
    }


@router.get("/nodes/{node_id}/config")
async def get_remote_config(node_id: str):
    """Poll status/result for the latest config read on a node."""
    if _reader is None:
        raise HTTPException(503, "Remote config reader not initialized")
    return _reader.get_status(node_id)


@router.post("/nodes/{node_id}/config/request")
async def request_remote_config(
    node_id: str,
    body: ConfigRequestBody | None = None,
    section: str | None = Query(default=None),
    claims: SessionClaims = Depends(require_admin),
    audit: AuditLogWriter = Depends(get_audit_writer),
):
    """Send one ADMIN get-config request to a remote node (read-only)."""
    if _reader is None:
        raise HTTPException(503, "Remote config reader not initialized")

    chosen = (body.section if body else None) or section or "device"
    params = {
        "target_node_id": node_id.strip().lower().lstrip("!"),
        "section": chosen,
    }

    with audit.timed_action(
        user=claims.subject,
        action="admin.config_request",
        params=params,
    ) as ctx:
        try:
            result = await _reader.request_config(node_id, section=chosen)
            ctx.params["packet_id"] = result.get("packet_id", "")
            ctx.params["request_id"] = result.get("request_id", "")
            ctx.params["status"] = result.get("status", "pending")
            return result
        except AdminConfigError as exc:
            raise HTTPException(exc.status_code, str(exc)) from exc
