"""USB companion firmware upload, flash, and live log WebSocket (PR 14)."""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Awaitable, Callable

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel, Field

from src.api.audit import AuditLogWriter
from src.api.audit.dependencies import get_audit_writer
from src.api.auth.dependencies import require_admin
from src.api.auth.jwt_session import ROLE_ADMIN, JwtSessionService, SessionClaims
from src.api.auth.ws_guard import WS_AUTH_CLOSE_CODE, authenticate_websocket
from src.firmware.flasher import FlashJob, get_port_lock, run_flash_job
from src.firmware.log_broadcast import FlashLogBroadcaster
from src.firmware.upload_store import FirmwareUploadStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/firmware", tags=["firmware"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
DEFAULT_BAUD = 460800
DEFAULT_OFFSET = "0x10000"

_upload_store = FirmwareUploadStore()
_broadcaster = FlashLogBroadcaster()
_jwt_service: JwtSessionService | None = None
_suspend_meshcore: Callable[[str], Awaitable[None]] | None = None
_default_port: str = "/dev/ttyUSB0"


def init_routes(
    *,
    jwt_service: JwtSessionService | None,
    suspend_meshcore: Callable[[str], Awaitable[None]] | None = None,
    default_serial_port: str | None = None,
) -> None:
    global _jwt_service, _suspend_meshcore, _default_port
    _jwt_service = jwt_service
    _suspend_meshcore = suspend_meshcore
    if default_serial_port:
        _default_port = default_serial_port


def reset_routes() -> None:
    global _jwt_service, _suspend_meshcore
    _jwt_service = None
    _suspend_meshcore = None


class FlashRequest(BaseModel):
    upload_id: str = Field(..., min_length=8, max_length=64)
    serial_port: str = Field(default="/dev/ttyUSB0", min_length=1, max_length=128)
    baud_rate: int = Field(default=DEFAULT_BAUD, ge=9600, le=921600)
    partition_offset: str = Field(default=DEFAULT_OFFSET, min_length=3, max_length=16)


@router.websocket("/ws/flash-log")
async def flash_log_ws(websocket: WebSocket) -> None:
    if _jwt_service is None:
        await websocket.accept()
        await websocket.close(code=WS_AUTH_CLOSE_CODE)
        return

    claims = authenticate_websocket(websocket, _jwt_service)
    if claims is None or claims.role != ROLE_ADMIN:
        await websocket.accept()
        await websocket.close(code=WS_AUTH_CLOSE_CODE)
        return

    await websocket.accept()
    await _broadcaster.subscribe(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await _broadcaster.unsubscribe(websocket)


@router.post("/upload")
async def upload_firmware(
    firmware_file: UploadFile = File(...),
    _claims: SessionClaims = Depends(require_admin),
):
    filename = (firmware_file.filename or "").strip()
    if not filename.lower().endswith(".bin"):
        raise HTTPException(status_code=400, detail="Only .bin firmware files are accepted.")

    content = await firmware_file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Firmware file exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.",
        )
    if not content:
        raise HTTPException(status_code=400, detail="Empty firmware file.")

    tmp = tempfile.NamedTemporaryFile(
        suffix=".bin",
        prefix="mp_fw_",
        delete=False,
    )
    try:
        tmp.write(content)
        tmp.flush()
        tmp.close()
        upload_id = _upload_store.store(
            Path(tmp.name),
            filename,
            len(content),
        )
    except Exception as exc:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to store upload: {exc}") from exc

    return {
        "upload_id": upload_id,
        "filename": filename,
        "size_bytes": len(content),
    }


@router.get("/defaults")
async def firmware_defaults(_claims: SessionClaims = Depends(require_admin)):
    return {
        "serial_port": _default_port,
        "baud_rate": DEFAULT_BAUD,
        "partition_offset": DEFAULT_OFFSET,
        "max_upload_bytes": MAX_UPLOAD_BYTES,
    }


@router.post("/flash")
async def flash_companion(
    req: FlashRequest,
    claims: SessionClaims = Depends(require_admin),
    audit: AuditLogWriter = Depends(get_audit_writer),
):
    record = _upload_store.pop(req.upload_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Unknown or expired upload_id.")

    port = req.serial_port.strip()
    if not port:
        raise HTTPException(status_code=400, detail="serial_port is required.")

    port_lock = get_port_lock(port)
    if port_lock.locked():
        _upload_store.store(record.path, record.filename, record.size_bytes)
        raise HTTPException(
            status_code=409,
            detail=f"A flash operation is already in progress on {port}.",
        )

    async def _task() -> None:
        async with port_lock:
            exit_code: int | None = None
            success = False
            with audit.timed_action(
                user=claims.subject,
                action="firmware_flash",
                params={
                    "filename": record.filename,
                    "port": port,
                    "baud": req.baud_rate,
                    "offset": req.partition_offset,
                    "size_bytes": record.size_bytes,
                },
            ) as ctx:
                try:
                    if _suspend_meshcore is not None:
                        await _broadcaster.broadcast(
                            f"[flasher] releasing MeshCore serial on {port}…"
                        )
                        await _suspend_meshcore(port)

                    job = FlashJob(
                        port=port,
                        baud=req.baud_rate,
                        offset=req.partition_offset,
                        bin_path=record.path,
                        log_callback=_broadcaster.broadcast,
                    )
                    success = await run_flash_job(job)
                    exit_code = 0 if success else 1
                    ctx.params["exit_code"] = exit_code
                    ctx.params["success"] = success
                    if not success:
                        ctx.set_result("error")
                except Exception as exc:
                    logger.exception("Firmware flash task failed")
                    await _broadcaster.broadcast(f"[flasher] EXCEPTION: {exc}")
                    ctx.set_result("error")
                    ctx.params["error"] = str(exc)
                finally:
                    try:
                        os.unlink(record.path)
                    except OSError:
                        pass
                    await _broadcaster.broadcast(
                        "[flasher] MeshCore will auto-reconnect when the port is free."
                    )

    asyncio.create_task(_task(), name="firmware-flash")

    return {
        "status": "queued",
        "port": port,
        "filename": record.filename,
        "ws_path": "/api/firmware/ws/flash-log",
    }
