"""Storm guard quarantine status and operator actions (PR 12)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from src.api.audit import AuditLogWriter
from src.api.audit.dependencies import get_audit_writer
from src.api.auth.dependencies import require_admin
from src.api.auth.jwt_session import SessionClaims
from src.config import AppConfig, save_section_to_yaml
from src.relay.node_id import normalize_node_id, validate_node_ids
from src.relay.relay_manager import RelayManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/relay", tags=["relay"])

_config: AppConfig | None = None
_relay_manager: RelayManager | None = None


def init_routes(
    config: AppConfig,
    relay_manager: RelayManager | None = None,
) -> None:
    global _config, _relay_manager
    _config = config
    _relay_manager = relay_manager


def reset_routes() -> None:
    global _config, _relay_manager
    _config = None
    _relay_manager = None


def _storm_guard():
    if _relay_manager is None or _relay_manager.storm_guard is None:
        return None
    return _relay_manager.storm_guard


@router.get("/quarantine")
async def list_quarantine():
    """Active in-memory quarantines (memory-only, not SQLite)."""
    guard = _storm_guard()
    if guard is None:
        return {"enabled": False, "entries": []}
    return {
        "enabled": guard.enabled,
        "entries": guard.snapshot(),
    }


@router.post("/quarantine/{node_id}/release")
async def release_quarantine(
    node_id: str,
    claims: SessionClaims = Depends(require_admin),
    audit: AuditLogWriter = Depends(get_audit_writer),
):
    guard = _storm_guard()
    if guard is None or not guard.enabled:
        raise HTTPException(status_code=404, detail="storm guard not enabled")

    key = normalize_node_id(node_id)
    if not key:
        raise HTTPException(status_code=400, detail="invalid node id")

    with audit.timed_action(
        user=claims.subject,
        action="relay.quarantine_release",
        params={"node_id": key},
    ):
        if not guard.release(key):
            raise HTTPException(status_code=404, detail="node not quarantined")

    return {"released": True, "node_id": key}


@router.post("/quarantine/{node_id}/blocklist")
async def promote_quarantine_to_blocklist(
    node_id: str,
    claims: SessionClaims = Depends(require_admin),
    audit: AuditLogWriter = Depends(get_audit_writer),
):
    """Release quarantine and add the node to the permanent relay blocklist."""
    if _config is None or _relay_manager is None:
        raise HTTPException(status_code=503, detail="relay not ready")

    guard = _storm_guard()
    if guard is None or not guard.enabled:
        raise HTTPException(status_code=404, detail="storm guard not enabled")

    key = normalize_node_id(node_id)
    if not key:
        raise HTTPException(status_code=400, detail="invalid node id")

    if guard.get_entry(key) is None:
        raise HTTPException(status_code=404, detail="node not quarantined")

    relay = _config.relay
    blocklist = list(relay.blocklist or [])
    if key not in blocklist:
        blocklist.append(key)

    with audit.timed_action(
        user=claims.subject,
        action="relay.quarantine_blocklist",
        params={"node_id": key},
    ):
        try:
            relay.blocklist = validate_node_ids(blocklist)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        save_section_to_yaml("relay", {"blocklist": relay.blocklist})
        guard.release(key)
        _relay_manager.reload_filters(blocklist=relay.blocklist)

    return {
        "blocklisted": True,
        "node_id": key,
        "blocklist": relay.blocklist,
    }
