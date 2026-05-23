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

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.api.audit import AuditLogWriter
from src.api.audit.dependencies import get_audit_writer
from src.api.auth.dependencies import require_admin
from src.api.auth.jwt_session import SessionClaims
from src.api.update.apply import ApplyResult, UpdateApplier
from src.api.update.channels import ReleaseChannelRegistry
from src.api.update.streaming import stream_update
from src.api.update.install_status import build_install_status_payload
from src.api.update.rollback_state import clear_rollback_state, write_rollback_state
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
_rollback_state_path: Path = Path("/opt/meshpoint/data/update_rollback.json")


def init_routes(
    applier: UpdateApplier,
    registry: ReleaseChannelRegistry,
    changelog_path: Path | None = None,
    rollback_state_path: Path | None = None,
) -> None:
    global _applier, _registry, _changelog_path, _rollback_state_path
    _applier = applier
    _registry = registry
    _changelog_path = changelog_path
    if rollback_state_path is not None:
        _rollback_state_path = rollback_state_path


def reset_routes() -> None:
    global _applier, _registry, _changelog_path, _rollback_state_path
    _applier = None
    _registry = None
    _changelog_path = None
    _rollback_state_path = Path("/opt/meshpoint/data/update_rollback.json")


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


class CheckUpdatesRequest(BaseModel):
    """Optional channel picker values; defaults to the live install branch."""

    channel_id: str | None = Field(default=None, max_length=64)
    custom_branch: str | None = Field(default=None, max_length=200)


@router.get("/channels")
async def list_channels(
    _claims: SessionClaims = Depends(require_admin),
) -> dict:
    _applier_instance, registry = _require_initialized()
    return {"channels": registry.to_payload()}


@router.get("/install_status")
async def install_status(
    _claims: SessionClaims = Depends(require_admin),
) -> dict:
    """Live install branch, matched channel, and upstream version on that branch."""
    _applier_instance, registry = _require_initialized()
    return build_install_status_payload(
        registry=registry,
        rollback_state_path=_rollback_state_path,
    )


@router.post("/check")
async def check_for_updates(
    req: CheckUpdatesRequest,
    _claims: SessionClaims = Depends(require_admin),
) -> dict:
    """Fetch origin and report how many commits HEAD is behind the target branch."""
    _applier_instance, registry = _require_initialized()
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        lambda: build_install_status_payload(
            registry=registry,
            sync_remote=True,
            channel_id=req.channel_id,
            custom_branch=req.custom_branch,
            rollback_state_path=_rollback_state_path,
        ),
    )


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


def _audit_apply_result(ctx, result: ApplyResult) -> None:
    ctx.params["success"] = result.success
    ctx.params["target_branch"] = result.target_branch
    if result.pre_update_sha:
        ctx.params["pre_update_sha"] = result.pre_update_sha
    if not result.success:
        ctx.params["failed_step"] = result.failed_step
        ctx.set_result("error")


def _persist_rollback_after_apply(result: ApplyResult) -> None:
    """Keep rollback SHA across dashboard reload after service restart."""
    if (
        result.success
        and result.pre_update_sha
        and result.target_branch != "rollback"
    ):
        write_rollback_state(
            result.pre_update_sha,
            target_branch=result.target_branch,
            path=_rollback_state_path,
        )


def _clear_rollback_after_success(result: ApplyResult) -> None:
    if result.success:
        clear_rollback_state(path=_rollback_state_path)


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
        _audit_apply_result(ctx, result)
        _persist_rollback_after_apply(result)
    return asdict(result)


@router.post("/apply/stream")
async def apply_update_stream(
    payload: ApplyRequest,
    claims: SessionClaims = Depends(require_admin),
    audit: AuditLogWriter = Depends(get_audit_writer),
) -> StreamingResponse:
    """Run apply and stream per-step progress as NDJSON (one object per line)."""
    applier, registry = _require_initialized()
    branch = registry.resolve_branch(
        payload.channel_id, custom_branch=payload.custom_branch,
    )
    if not branch:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid_channel_or_branch",
        )

    async def body() -> AsyncIterator[bytes]:
        result: ApplyResult | None = None
        with audit.timed_action(
            user=claims.subject,
            action="update.apply.stream",
            params={"channel_id": payload.channel_id, "branch": branch},
        ) as ctx:
            async for chunk in stream_update(
                applier, mode="apply", branch=branch,
            ):
                yield chunk
                line = chunk.decode("utf-8").strip()
                if not line:
                    continue
                event = json.loads(line)
                if event.get("type") == "result":
                    result_dict = event.get("result")
                    if result_dict:
                        result = ApplyResult(**result_dict)
                        _audit_apply_result(ctx, result)
                        _persist_rollback_after_apply(result)
            if result is None:
                ctx.set_result("error")

    return StreamingResponse(
        body(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


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
        _clear_rollback_after_success(result)
    return asdict(result)


@router.post("/rollback/stream")
async def rollback_update_stream(
    payload: RollbackRequest,
    claims: SessionClaims = Depends(require_admin),
    audit: AuditLogWriter = Depends(get_audit_writer),
) -> StreamingResponse:
    """Roll back and stream per-step progress as NDJSON."""
    applier, _registry_instance = _require_initialized()

    async def body() -> AsyncIterator[bytes]:
        result: ApplyResult | None = None
        with audit.timed_action(
            user=claims.subject,
            action="update.rollback.stream",
            params={"sha": payload.sha},
        ) as ctx:
            async for chunk in stream_update(
                applier, mode="rollback", sha=payload.sha,
            ):
                yield chunk
                line = chunk.decode("utf-8").strip()
                if not line:
                    continue
                event = json.loads(line)
                if event.get("type") == "result":
                    result_dict = event.get("result")
                    if result_dict:
                        result = ApplyResult(**result_dict)
                        ctx.params["success"] = result.success
                        if not result.success:
                            ctx.params["failed_step"] = result.failed_step
                            ctx.set_result("error")
                        _clear_rollback_after_success(result)
            if result is None:
                ctx.set_result("error")

    return StreamingResponse(
        body(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
