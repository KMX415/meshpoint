"""Download and flash official Meshtastic firmware (ESP + nRF).

ESP boards use esptool ``.factory.bin``; nRF52840 boards use Adafruit
serial DFU on ``-ota.zip``. Credit: javastraat/meshpoint (firmware flash port).
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.api.audit import AuditLogWriter
from src.api.audit.dependencies import get_audit_writer
from src.api.auth.dependencies import require_admin
from src.api.auth.jwt_session import SessionClaims
from src.api.firmware import (
    WRITE_FLASH_SUBCOMMAND,
    EspToolBinaryResolver,
    EspToolNdjsonStreamer,
)
from src.api.firmware.firmware_upload_store import FirmwareUploadStore
from src.api.firmware.meshtastic_firmware_catalog import MeshtasticFirmwareAssetCatalog
from src.api.firmware.nrf_flash_session import NrfFlashSession
from src.config import AppConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config/serial/firmware", tags=["config", "serial"])

_config: Optional[AppConfig] = None
_serial_sources: list = []

_CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "meshtastic-firmware"
_catalog = MeshtasticFirmwareAssetCatalog(cache_dir=_CACHE_DIR)
_uploads = FirmwareUploadStore(_CACHE_DIR / "uploads")
_streamer = EspToolNdjsonStreamer()
_esptool = EspToolBinaryResolver()
_nrf = NrfFlashSession(streamer=_streamer)


def init_routes(config: AppConfig, serial_sources=None) -> None:
    global _config, _serial_sources
    _config = config
    _serial_sources = serial_sources or []


def _resolve_serial_source(label: str):
    name = f"serial_{label}" if label else "serial"
    for src in _serial_sources:
        if src.name == name:
            return src
    return None


def _ndjson(payload: dict) -> bytes:
    return _streamer.ndjson(payload)


@router.get("/installed")
async def firmware_installed(
    _claims: SessionClaims = Depends(require_admin),
) -> dict:
    from src.capture.serial_firmware_info import SerialFirmwareInfoReader

    reader = SerialFirmwareInfoReader()
    devices = [reader.read_from_source(src) for src in _serial_sources]
    return {"devices": devices}


def _resolve_release_sync(tag: str) -> dict:
    return _catalog.resolve_release_sync(tag)


def _releases_sync(limit: int = 10) -> list[dict]:
    return _catalog.releases_sync(limit)


def _manifest_from_release_sync(release: dict) -> dict:
    return _catalog.manifest_from_release_sync(release)


def _board_list_from_manifest_sync(manifest: dict) -> list[dict]:
    return _catalog.board_list_from_manifest_sync(manifest)


def _ensure_board_firmware_cached_sync(board: str, tag: str = "") -> dict:
    return _catalog.ensure_board_firmware_cached_sync(board, tag=tag)


@router.get("/targets")
async def firmware_targets(
    tag: str = "",
    _claims: SessionClaims = Depends(require_admin),
) -> dict:
    loop = asyncio.get_running_loop()
    try:
        release = await loop.run_in_executor(None, _catalog.resolve_release_sync, tag)
        manifest = await loop.run_in_executor(
            None, _catalog.manifest_from_release_sync, release,
        )
        boards = _catalog.board_list_from_manifest_sync(manifest)
    except Exception as exc:
        raise HTTPException(502, f"Could not fetch Meshtastic board list: {exc}")
    return {"boards": boards, "tag": release.get("tag_name", "")}


@router.get("/releases")
async def firmware_releases(_claims: SessionClaims = Depends(require_admin)) -> dict:
    loop = asyncio.get_running_loop()
    try:
        releases = await loop.run_in_executor(None, _catalog.releases_sync, 10)
    except Exception as exc:
        raise HTTPException(502, f"Could not fetch Meshtastic releases: {exc}")
    return {
        "releases": [
            {"tag": r.get("tag_name", ""), "published_at": r.get("published_at")}
            for r in releases
        ],
    }


@router.post("/upload")
async def firmware_upload(
    file: UploadFile = File(...),
    _claims: SessionClaims = Depends(require_admin),
) -> dict:
    data = await file.read()
    try:
        upload_id = _uploads.save(file.filename or "firmware.bin", data)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return {"upload_id": upload_id, "filename": file.filename}


def _port_aliases(port: str) -> set[str]:
    from src.hal.usb_classifier import list_serial_ports_with_stable_paths

    aliases = {port}
    for dev in list_serial_ports_with_stable_paths():
        values = {dev.device, dev.stable_path, dev.by_id, dev.by_path}
        if port in values:
            aliases.update(v for v in values if v)
    return aliases


def _match_serial_source(port: str):
    label = ""
    source = None
    if _config is None:
        return label, source
    aliases = _port_aliases(port)
    for d in _config.capture.serial:
        if d.serial_port and d.serial_port in aliases:
            label = d.label or ""
            source = _resolve_serial_source(label)
            return label, source
    if _config.capture.serial_port and _config.capture.serial_port in aliases:
        source = _resolve_serial_source("")
    return label, source


class FlashRequest(BaseModel):
    board: str
    port: str
    tag: str = ""
    erase_all: bool = False
    upload_id: str = ""
    flash_mode: str = ""


@router.post("/flash/stream")
async def flash_meshtastic_stream(
    req: FlashRequest,
    claims: SessionClaims = Depends(require_admin),
    audit: AuditLogWriter = Depends(get_audit_writer),
) -> StreamingResponse:
    if not req.board and not req.upload_id:
        raise HTTPException(400, "No board selected")

    from src.hal.usb_classifier import list_serial_ports_with_stable_paths

    real_ports = {
        value
        for dev in list_serial_ports_with_stable_paths()
        if dev.vid is not None
        for value in (dev.device, dev.stable_path, dev.by_id, dev.by_path)
        if value
    }
    if req.port not in real_ports:
        raise HTTPException(
            400, "Selected port is not a currently connected USB-serial device",
        )
    port = req.port
    label, source = _match_serial_source(port)

    async def body() -> AsyncIterator[bytes]:
        with audit.timed_action(
            user=claims.subject,
            action="meshtastic_firmware.flash",
            params={
                "board": req.board,
                "label": label,
                "port": port,
                "tag": req.tag or "latest",
                "erase_all": req.erase_all,
                "upload_id": req.upload_id or None,
            },
        ) as ctx:
            loop = asyncio.get_running_loop()
            uploaded = _uploads.resolve(req.upload_id) if req.upload_id else None
            fw = None
            flash_method = "esptool"

            if uploaded is not None:
                flash_method = "nrf_dfu"
                yield _ndjson({
                    "type": "line",
                    "stream": "stdout",
                    "text": f"Using uploaded firmware {uploaded.name}.",
                })
            else:
                yield _ndjson({
                    "type": "line",
                    "stream": "stdout",
                    "text": (
                        f"Fetching Meshtastic {req.tag or 'latest'} for "
                        f"{req.board.replace('-', ' ')}…"
                    ),
                })
                try:
                    fw = await loop.run_in_executor(
                        None, _catalog.ensure_board_firmware_cached_sync,
                        req.board, req.tag,
                    )
                except Exception as exc:
                    logger.exception(
                        "Meshtastic firmware fetch failed for %s", req.board,
                    )
                    yield _ndjson({
                        "type": "line", "stream": "stderr", "text": str(exc),
                    })
                    yield _ndjson({
                        "type": "result",
                        "result": {
                            "returncode": -1, "success": False, "error": str(exc),
                        },
                    })
                    ctx.set_result("error")
                    return
                flash_method = fw["flash_method"]
                yield _ndjson({
                    "type": "line",
                    "stream": "stdout",
                    "text": (
                        f"Using Meshtastic {fw['version']} "
                        f"({fw.get('mcu')}, {flash_method})."
                    ),
                })

            if flash_method == "nrf_dfu":
                package = uploaded
                mode = req.flash_mode or "dfu"
                if package is None and fw is not None:
                    if mode == "uf2":
                        package = fw.get("uf2")
                        if package is None:
                            yield _ndjson({
                                "type": "line",
                                "stream": "stderr",
                                "text": "No UF2 asset cached for this board.",
                            })
                            yield _ndjson({
                                "type": "result",
                                "result": {
                                    "returncode": -1,
                                    "success": False,
                                    "error": "missing uf2",
                                },
                            })
                            ctx.set_result("error")
                            return
                    else:
                        package = fw["dfu_zip"]
                elif package is not None and package.suffix.lower() == ".uf2":
                    mode = "uf2"

                async def _release():
                    await source.stop()

                async def _restore():
                    await source.start()

                success = False
                async for chunk in _nrf.run(
                    package=package,
                    port=port,
                    mode=mode,
                    release_source=_release if source is not None else None,
                    restore_source=_restore if source is not None else None,
                    reconnect_sleep_s=5.0,
                    source_name=source.name if source else "serial",
                ):
                    yield chunk
                    event = json.loads(chunk)
                    if event.get("type") == "result":
                        success = bool((event.get("result") or {}).get("success"))
                ctx.set_result("success" if success else "error")
                return

            released = source is not None
            if released:
                yield _ndjson({
                    "type": "line",
                    "stream": "stdout",
                    "text": (
                        f"Releasing {port} ({source.name}"
                        f"{'' if source.connected else ' reconnect loop'})…"
                    ),
                })
                await source.stop()

            missing = _esptool.missing_install_hint()
            if missing:
                yield _ndjson({
                    "type": "line", "stream": "stderr", "text": missing,
                })
                yield _ndjson({
                    "type": "result",
                    "result": {
                        "returncode": -1, "success": False, "error": missing,
                    },
                })
                if released:
                    await source.start()
                ctx.set_result("error")
                return

            write_flash_args = ["0x0", str(fw["factory_bin"])]
            if (
                req.erase_all
                and fw["littlefs_bin"]
                and fw["littlefs_offset"] is not None
            ):
                write_flash_args += [
                    hex(fw["littlefs_offset"]), str(fw["littlefs_bin"]),
                ]
            cmd = [
                *_esptool.resolve_argv(),
                "--chip", fw["mcu"], "--port", port, "--baud", "921600",
                WRITE_FLASH_SUBCOMMAND,
                *(["--erase-all"] if req.erase_all else []),
                *write_flash_args,
            ]
            success = False
            async for chunk in _streamer.stream_subprocess(cmd):
                yield chunk
                event = json.loads(chunk)
                if event.get("type") == "result":
                    success = bool((event.get("result") or {}).get("success"))

            if released:
                if not success:
                    yield _ndjson({
                        "type": "line",
                        "stream": "stderr",
                        "text": (
                            "Flash failed (esptool exited non-zero). "
                            "Restoring USB capture…"
                        ),
                    })
                    await source.start()
                else:
                    yield _ndjson({
                        "type": "line",
                        "stream": "stdout",
                        "text": "Waiting for the board to finish rebooting…",
                    })
                    await asyncio.sleep(3.0)
                    await source.start()
                    yield _ndjson({
                        "type": "line",
                        "stream": "stdout",
                        "text": (
                            f"{source.name} reconnected on {port}."
                            if source.connected
                            else f"{source.name} did NOT reconnect."
                        ),
                    })
            ctx.set_result("success" if success else "error")

    return StreamingResponse(
        body(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
