"""HTTP surface for the dashboard update + watchdog flow.

Three endpoints, all admin-only, all audited:

* ``GET  /api/update/channels`` -- enumerate available release tracks
  for the picker.
* ``POST /api/update/apply``    -- run the apply chain on the
  selected channel; returns the structured ``ApplyResult``.
* ``POST /api/update/rollback`` -- restore a prior SHA + restart
  service.

The route layer never spawns subprocesses directly: it asks the
injected :class:`UpdateApplier` to do the work. Tests provide a fake
applier so the suite never shells out.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.api.audit import AuditLogWriter
from src.api.audit.dependencies import get_audit_writer
from src.api.auth.dependencies import require_admin
from src.api.auth.jwt_session import SessionClaims
from src.api.update.apply import UpdateApplier
from src.api.update.channels import ReleaseChannelRegistry
from src.api.update.release_notes import (
    ChangelogParser,
    format_section_for_preview,
    select_preview_section,
)
from src.version import __version__ as INSTALLED_VERSION

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/update", tags=["update"])

_applier: UpdateApplier | None = None
_registry: ReleaseChannelRegistry | None = None
_changelog_path: Path | None = None


def init_routes(
    applier: UpdateApplier,
    registry: ReleaseChannelRegistry,
    changelog_path: Path | None = None,
) -> None:
    global _applier, _registry, _changelog_path
    _applier = applier
    _registry = registry
    _changelog_path = changelog_path


def reset_routes() -> None:
    global _applier, _registry, _changelog_path
    _applier = None
    _registry = None
    _changelog_path = None


def _require_initialized() -> tuple[UpdateApplier, ReleaseChannelRegistry]:
    if _applier is None or _registry is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="update subsystem not initialized",
        )
    return _applier, _registry


class ApplyRequest(BaseModel):
    channel_id: str = Field(..., min_length=1, max_length=64)
    custom_branch: str | None = Field(default=None, max_length=200)


class RollbackRequest(BaseModel):
    sha: str = Field(..., min_length=4, max_length=80)


@router.get("/channels")
async def list_channels(
    _claims: SessionClaims = Depends(require_admin),
) -> dict:
    _applier_instance, registry = _require_initialized()
    return {"channels": registry.to_payload()}


@router.get("/release_notes")
async def release_notes(
    channel_id: str = Query(..., min_length=1, max_length=64),
    _claims: SessionClaims = Depends(require_admin),
) -> dict:
    _applier_instance, registry = _require_initialized()
    channel = registry.find(channel_id)
    if channel is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid_channel",
        )
    sections = _load_changelog_sections()
    preview = select_preview_section(
        sections,
        tier=channel.tier,
        channel_id=channel.id,
        installed_version=INSTALLED_VERSION,
    )
    return {
        "channel_id": channel.id,
        "channel_label": channel.label,
        "channel_tier": channel.tier,
        "current_installed_version": INSTALLED_VERSION,
        "preview_section": (
            format_section_for_preview(preview) if preview is not None else None
        ),
    }


def _load_changelog_sections() -> list:
    if _changelog_path is None or not _changelog_path.exists():
        return []
    try:
        return ChangelogParser.parse_file(_changelog_path)
    except OSError as exc:
        logger.warning("release_notes: could not read changelog: %s", exc)
        return []


@router.post("/apply")
async def apply_update(
    payload: ApplyRequest,
    claims: SessionClaims = Depends(require_admin),
    audit: AuditLogWriter = Depends(get_audit_writer),
) -> dict:
    applier, registry = _require_initialized()
    branch = registry.resolve_branch(
        payload.channel_id, custom_branch=payload.custom_branch,
    )
    if not branch:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid_channel_or_branch",
        )
    with audit.timed_action(
        user=claims.subject,
        action="update.apply",
        params={"channel_id": payload.channel_id, "branch": branch},
    ) as ctx:
        result = applier.apply(branch=branch)
        ctx.params["success"] = result.success
        ctx.params["target_branch"] = result.target_branch
        if not result.success:
            ctx.params["failed_step"] = result.failed_step
            ctx.set_result("error")
    return asdict(result)


@router.post("/rollback")
async def rollback_update(
    payload: RollbackRequest,
    claims: SessionClaims = Depends(require_admin),
    audit: AuditLogWriter = Depends(get_audit_writer),
) -> dict:
    applier, _registry_instance = _require_initialized()
    with audit.timed_action(
        user=claims.subject,
        action="update.rollback",
        params={"sha": payload.sha},
    ) as ctx:
        result = applier.rollback(sha=payload.sha)
        ctx.params["success"] = result.success
        if not result.success:
            ctx.params["failed_step"] = result.failed_step
            ctx.set_result("error")
    return asdict(result)
