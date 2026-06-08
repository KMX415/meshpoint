"""Remote Meshtastic ADMIN config read/write routes (PR 15–16)."""
from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.admin.pending_store import DEBOUNCE_SECONDS, REQUEST_TIMEOUT_SECONDS
from src.admin.reader import AdminConfigError, AdminConfigReader
from src.admin.write_store import WRITE_DEBOUNCE_SECONDS
from src.admin.writer import AdminConfigWriter
from src.api.audit import AuditLogWriter
from src.api.audit.dependencies import get_audit_writer
from src.api.auth.dependencies import require_admin
from src.api.auth.jwt_session import SessionClaims

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])

_reader: AdminConfigReader | None = None
_writer: AdminConfigWriter | None = None


def init_routes(
    *,
    reader: AdminConfigReader | None,
    writer: AdminConfigWriter | None = None,
) -> None:
    global _reader, _writer
    _reader = reader
    _writer = writer


def reset_routes() -> None:
    global _reader, _writer
    _reader = None
    _writer = None


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
            "write_debounce_seconds": WRITE_DEBOUNCE_SECONDS,
            "writable_fields": [
                "long_name",
                "short_name",
                "role",
                "screen_on_secs",
                "telemetry_interval_secs",
            ],
        }
    return {
        "available": _reader.available,
        "debounce_seconds": DEBOUNCE_SECONDS,
        "timeout_seconds": REQUEST_TIMEOUT_SECONDS,
        "write_debounce_seconds": WRITE_DEBOUNCE_SECONDS,
        "writable_fields": [
            "long_name",
            "short_name",
            "role",
            "screen_on_secs",
            "telemetry_interval_secs",
        ],
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


class ConfigWriteBody(BaseModel):
    long_name: str | None = Field(default=None, max_length=40)
    short_name: str | None = Field(default=None, max_length=4)
    role: int | None = Field(default=None, ge=0, le=11)
    role_confirm: str | None = Field(default=None, max_length=16)
    screen_on_secs: int | None = Field(default=None, ge=0, le=600)
    telemetry_interval_secs: int | None = Field(default=None, ge=30, le=86400)


@router.get("/nodes/{node_id}/config/write")
async def get_remote_config_write_status(node_id: str):
    """Poll status for the latest config write + verify on a node."""
    if _writer is None:
        raise HTTPException(503, "Remote config writer not initialized")
    return _writer.get_status(node_id)


@router.post("/nodes/{node_id}/config/write")
async def write_remote_config(
    node_id: str,
    body: ConfigWriteBody,
    claims: SessionClaims = Depends(require_admin),
    audit: AuditLogWriter = Depends(get_audit_writer),
):
    """Apply allow-listed ADMIN config writes; auto-read verifies afterward."""
    if _writer is None:
        raise HTTPException(503, "Remote config writer not initialized")

    params = {
        "target_node_id": node_id.strip().lower().lstrip("!"),
        "changes": body.model_dump(exclude_none=True, exclude={"role_confirm"}),
    }
    if body.role is not None:
        params["role_change"] = True

    with audit.timed_action(
        user=claims.subject,
        action="admin.config_write",
        params=params,
    ) as ctx:
        try:
            result = await _writer.apply_changes(
                node_id,
                long_name=body.long_name,
                short_name=body.short_name,
                role=body.role,
                role_confirm=body.role_confirm,
                screen_on_secs=body.screen_on_secs,
                telemetry_interval_secs=body.telemetry_interval_secs,
            )
            ctx.params["operation_id"] = result.get("operation_id", "")
            ctx.params["status"] = result.get("status", "")
            ctx.params["verify_sections"] = result.get("verify_sections", [])
            return result
        except AdminConfigError as exc:
            raise HTTPException(exc.status_code, str(exc)) from exc
