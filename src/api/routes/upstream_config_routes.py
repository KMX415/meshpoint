"""Meshradar cloud uplink settings for the Configuration panel."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.audit import AuditLogWriter
from src.api.audit.dependencies import get_audit_writer
from src.api.auth.dependencies import require_admin
from src.api.auth.jwt_session import SessionClaims
from src.config import AppConfig, save_section_to_yaml

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])

_config: AppConfig | None = None


def init_routes(config: AppConfig) -> None:
    global _config
    _config = config


def reset_routes() -> None:
    global _config
    _config = None


def build_upstream_status(upstream) -> dict:
    """Dashboard shape for Meshradar uplink tuning.

    ``upstream.enabled`` is intentionally omitted: disabling cloud uplink
    stays a ``local.yaml`` / wizard concern, not a dashboard toggle.
    """
    token = (upstream.auth_token or "").strip()
    return {
        "url": upstream.url,
        "reconnect_interval_seconds": upstream.reconnect_interval_seconds,
        "buffer_max_size": upstream.buffer_max_size,
        "auth_token_set": bool(token),
    }


class UpstreamUpdate(BaseModel):
    url: str = "wss://api.meshradar.io"
    reconnect_interval_seconds: int = Field(10, ge=1, le=3600)
    buffer_max_size: int = Field(5000, ge=100, le=100_000)
    auth_token: str | None = None
    auth_token_unchanged: bool = True


@router.put("/upstream")
async def update_upstream(
    req: UpstreamUpdate,
    _claims: SessionClaims = Depends(require_admin),
    audit: AuditLogWriter = Depends(get_audit_writer),
):
    """Persist Meshradar uplink settings. Requires service restart."""
    if _config is None:
        raise HTTPException(503, "Config not loaded")

    url = req.url.strip()
    if not url.startswith(("ws://", "wss://")):
        raise HTTPException(400, "Upstream URL must start with ws:// or wss://")

    updates: dict = {
        "url": url,
        "reconnect_interval_seconds": req.reconnect_interval_seconds,
        "buffer_max_size": req.buffer_max_size,
    }

    if not req.auth_token_unchanged and req.auth_token is not None:
        token = req.auth_token.strip()
        if _config.upstream.enabled and not token:
            raise HTTPException(
                400,
                "API key is required while Meshradar uplink is enabled",
            )
        updates["auth_token"] = token or None

    with audit.timed_action(
        user=_claims.subject,
        action="config.upstream_update",
        params={"url": url},
    ):
        upstream = _config.upstream
        upstream.url = updates["url"]
        upstream.reconnect_interval_seconds = updates["reconnect_interval_seconds"]
        upstream.buffer_max_size = updates["buffer_max_size"]
        if "auth_token" in updates:
            upstream.auth_token = updates["auth_token"]

        try:
            save_section_to_yaml("upstream", updates)
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    logger.info("Upstream config updated: url=%s", url)

    return {
        "saved": True,
        "restart_required": True,
        "upstream": build_upstream_status(upstream),
    }
