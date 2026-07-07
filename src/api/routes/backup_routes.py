"""HTTP surface for Meshpoint configuration backup and restore."""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from src.api.audit import AuditLogWriter
from src.api.audit.dependencies import get_audit_writer
from src.api.auth.dependencies import require_admin
from src.api.auth.jwt_session import SessionClaims
from src.api.routes.system_metrics import system_metrics
from src.backup.archive_builder import BackupArchiveBuilder
from src.backup.paths import (
    MAX_UPLOAD_BYTES,
    is_excluded_data_relative,
    resolve_data_dir,
    resolve_local_config_path,
)
from src.backup.restore_service import BackupRestoreService, RestoreValidationError
from src.config import AppConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system/backup", tags=["backup"])

_config: AppConfig | None = None


def init_routes(config: AppConfig) -> None:
    global _config
    _config = config


def reset_routes() -> None:
    global _config
    _config = None


def _require_config() -> AppConfig:
    if _config is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="backup_routes_not_initialized",
        )
    return _config


def _estimate_backup_bytes(config: AppConfig) -> int:
    total = 0
    local_path = resolve_local_config_path()
    if local_path.is_file():
        total += local_path.stat().st_size

    data_dir = resolve_data_dir(config.storage.database_path)
    if not data_dir.is_dir():
        return total

    db_name = Path(config.storage.database_path).name
    for path in data_dir.rglob("*"):
        if not path.is_file():
            continue
        rel_parts = path.relative_to(data_dir).parts
        if is_excluded_data_relative(rel_parts):
            continue
        if path.name in {f"{db_name}-wal", f"{db_name}-shm"}:
            continue
        total += path.stat().st_size
    return total


@router.get("/status")
async def backup_status(
    _claims: SessionClaims = Depends(require_admin),
) -> dict:
    config = _require_config()
    metrics = await system_metrics()
    disk_percent = float(metrics.get("disk_percent", 0))
    return {
        "device_id": config.device.device_id,
        "device_name": config.device.device_name,
        "includes": [
            "config/local.yaml",
            "data/ (full directory, SQLite hot snapshot)",
        ],
        "estimated_bytes": _estimate_backup_bytes(config),
        "disk_percent": disk_percent,
        "suggest_backup": disk_percent >= 90,
        "encryption": "none",
        "max_upload_bytes": MAX_UPLOAD_BYTES,
    }


@router.get("/download")
async def download_backup(
    claims: SessionClaims = Depends(require_admin),
    audit: AuditLogWriter = Depends(get_audit_writer),
):
    config = _require_config()
    builder = BackupArchiveBuilder(
        local_config_path=resolve_local_config_path(),
        data_dir=resolve_data_dir(config.storage.database_path),
        database_path=config.storage.database_path,
        device_id=config.device.device_id,
        device_name=config.device.device_name,
    )

    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(None, builder.build)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="local_config_missing",
        ) from exc

    with audit.timed_action(user=claims.subject, action="backup.download") as ctx:
        ctx.params["device_id"] = config.device.device_id
        ctx.params["entry_count"] = len(result.manifest.entries)
        ctx.params["total_bytes"] = result.manifest.total_bytes

    def _cleanup(path: Path) -> None:
        try:
            os.unlink(path)
        except OSError:
            pass

    return FileResponse(
        path=result.archive_path,
        media_type="application/gzip",
        filename=result.download_filename,
        background=BackgroundTask(_cleanup, result.archive_path),
    )


@router.post("/restore")
async def restore_backup(
    request: Request,
    claims: SessionClaims = Depends(require_admin),
    audit: AuditLogWriter = Depends(get_audit_writer),
) -> dict:
    config = _require_config()
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            declared = int(content_length)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="invalid_content_length",
            ) from exc
        if declared > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="archive_too_large",
            )
        if declared == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="empty_upload",
            )

    payload = await request.body()
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="empty_upload",
        )
    if len(payload) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="archive_too_large",
        )

    data_dir = resolve_data_dir(config.storage.database_path)
    service = BackupRestoreService(data_dir=data_dir)

    try:
        manifest = service.validate_archive_bytes(payload)
    except RestoreValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    archive_path = service.save_validated_upload(payload, manifest=manifest)

    with audit.timed_action(user=claims.subject, action="backup.restore") as ctx:
        ctx.params["device_id"] = manifest.device_id
        ctx.params["backup_version"] = manifest.meshpoint_version
        ctx.params["archive_path"] = str(archive_path)

    try:
        launch = service.launch_restore(archive_path)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="restore_script_missing",
        ) from exc

    return {
        "success": True,
        "message": launch.message,
        "stash_path": launch.stash_hint,
        "device_id": manifest.device_id,
        "backup_version": manifest.meshpoint_version,
    }
