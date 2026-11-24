"""Download and flash official MeshCore companion firmware (ESP + nRF).

Fetches companion- tagged releases from meshcore-dev/MeshCore. ESP boards
use esptool ``*-merged.bin``; nRF boards use Adafruit serial DFU on ``.zip``.
Credit: javastraat/meshpoint (firmware flash port).
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
from src.api.firmware.meshcore_firmware_catalog import (
    FLAVORS,
    MeshcoreFirmwareAssetCatalog,
)
from src.api.firmware.nrf_flash_session import NrfFlashSession
from src.config import AppConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config/meshcore/firmware", tags=["config", "meshcore"])

_config: Optional[AppConfig] = None
_meshcore_sources: list = []
_tx_service = None

_CACHE_DIR = Path(__file__).resolve().parents[3] / "data" / "meshcore-firmware"
_catalog = MeshcoreFirmwareAssetCatalog(cache_dir=_CACHE_DIR)
_uploads = FirmwareUploadStore(_CACHE_DIR / "uploads")
_streamer = EspToolNdjsonStreamer()
_esptool = EspToolBinaryResolver()
_nrf = NrfFlashSession(streamer=_streamer)


def init_routes(config: AppConfig, meshcore_sources=None, tx_service=None) -> None:
    global _config, _meshcore_sources, _tx_service
    _config = config
    _meshcore_sources = meshcore_sources or []
    _tx_service = tx_service


def _resolve_meshcore_tx():
    if _tx_service is None:
        return None
    return getattr(_tx_service, "_meshcore_tx", None)


def _resolve_meshcore_source(label: str):
    name = f"meshcore_usb_{label}" if label else "meshcore_usb"
    for src in _meshcore_sources:
        if src.name == name:
            return src
    return None


def _ndjson(payload: dict) -> bytes:
    return _streamer.ndjson(payload)


@router.get("/installed")
async def firmware_installed(
    _claims: SessionClaims = Depends(require_admin),
) -> dict:
    mc_tx = _resolve_meshcore_tx()
    source = next(
        (s for s in _meshcore_sources if getattr(s, "name", "") == "meshcore_usb"),
        _meshcore_sources[0] if _meshcore_sources else None,
    )
    port = None
    if source is not None:
        port = (
            getattr(source, "_resolved_port", None)
            or getattr(source, "serial_port", None)
        )
    connected = bool(mc_tx and mc_tx.connected)
    payload = {
        "connected": connected,
        "port": port,
        "version": "",
        "model": "",
        "build": "",
        "name": getattr(source, "name", "meshcore_usb") if source else "meshcore_usb",
    }
    if not connected or mc_tx is None:
        return payload
    info = await mc_tx.get_device_info()
    if info:
        payload.update({
            "version": info.get("version") or "",
            "model": info.get("model") or "",
            "build": info.get("build") or "",
        })
    return payload


@router.get("/targets")
async def firmware_targets(
    tag: str = "",
    flavor: str = "usb",
    _claims: SessionClaims = Depends(require_admin),
) -> dict:
    if flavor not in FLAVORS:
        raise HTTPException(400, f"Unknown flavor, expected one of {FLAVORS}")
    loop = asyncio.get_running_loop()
    try:
        release = await loop.run_in_executor(None, _catalog.resolve_release_sync, tag)
        boards = await loop.run_in_executor(
            None, _catalog.board_list_from_release_sync, release, flavor,
        )
    except Exception as exc:
        raise HTTPException(502, f"Could not fetch MeshCore board list: {exc}")
    return {"boards": boards, "tag": release.get("tag_name", "")}


@router.get("/releases")
async def firmware_releases(_claims: SessionClaims = Depends(require_admin)) -> dict:
    loop = asyncio.get_running_loop()
    try:
        releases = await loop.run_in_executor(
            None, _catalog.companion_releases_sync, 10,
        )
    except Exception as exc:
        raise HTTPException(502, f"Could not fetch MeshCore releases: {exc}")
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


# Test / catalog shims (keep existing unit tests working)
def _companion_releases_sync(limit: int = 10) -> list[dict]:
    return _catalog.companion_releases_sync(limit)


def _board_list_from_release_sync(release: dict, flavor: str) -> list[dict]:
    return _catalog.board_list_from_release_sync(release, flavor)


def _ensure_board_firmware_cached_sync(
    board: str, tag: str = "", flavor: str = "usb",
) -> dict:
    return _catalog.ensure_board_firmware_cached_sync(board, tag=tag, flavor=flavor)


def _port_aliases(port: str) -> set[str]:
    from src.hal.usb_classifier import list_serial_ports_with_stable_paths

    aliases = {port}
    for dev in list_serial_ports_with_stable_paths():
        values = {dev.device, dev.stable_path, dev.by_id, dev.by_path}
        if port in values:
            aliases.update(v for v in values if v)
    return aliases


def _match_meshcore_source(port: str):
    if _config is None:
        return "", None
    aliases = _port_aliases(port)
    mc = _config.capture.meshcore_usb
    if mc.serial_port and mc.serial_port in aliases:
        return "", _resolve_meshcore_source("")
    for src in _meshcore_sources:
        candidates = {
            getattr(src, "_resolved_port", None),
            getattr(src, "_configured_port", None),
            getattr(src, "serial_port", None),
        }
        if aliases & {c for c in candidates if c}:
            return "", src
    return "", None


class FlashRequest(BaseModel):
    board: str
    port: str
    tag: str = ""
    flavor: str = "usb"
    erase_all: bool = False
    upload_id: str = ""
    flash_mode: str = ""  # "", "dfu", "uf2"


@router.post("/flash/stream")
async def flash_meshcore_stream(
    req: FlashRequest,
    claims: SessionClaims = Depends(require_admin),
    audit: AuditLogWriter = Depends(get_audit_writer),
) -> StreamingResponse:
    if not req.board and not req.upload_id:
        raise HTTPException(400, "No board selected")
    if req.flavor not in FLAVORS:
        raise HTTPException(400, f"Unknown flavor, expected one of {FLAVORS}")

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
    label, source = _match_meshcore_source(port)

    async def body() -> AsyncIterator[bytes]:
        with audit.timed_action(
            user=claims.subject,
            action="meshcore_firmware.flash",
            params={
                "board": req.board,
                "label": label,
                "port": port,
                "tag": req.tag or "latest",
                "flavor": req.flavor,
                "erase_all": req.erase_all,
                "upload_id": req.upload_id or None,
            },
        ) as ctx:
            loop = asyncio.get_running_loop()
            uploaded = _uploads.resolve(req.upload_id) if req.upload_id else None
            fw = None
            flash_method = "esptool"
            if uploaded is not None:
                flash_method = "nrf_dfu" if uploaded.suffix.lower() in {
                    ".zip", ".uf2",
                } else "esptool"
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
                        f"Fetching MeshCore {req.tag or 'latest'} ({req.flavor}) "
                        f"for {req.board.replace('_', ' ')}…"
                    ),
                })
                try:
                    fw = await loop.run_in_executor(
                        None,
                        _catalog.ensure_board_firmware_cached_sync,
                        req.board,
                        req.tag,
                        req.flavor,
                    )
                except Exception as exc:
                    logger.exception("MeshCore firmware fetch failed for %s", req.board)
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
                    "text": f"Using MeshCore {fw['tag']} ({fw['flavor']}, {flash_method}).",
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
                elif package is not None:
                    mode = "dfu"

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
                    reconnect_sleep_s=10.0,
                    source_name=source.name if source else "meshcore_usb",
                ):
                    yield chunk
                    event = json.loads(chunk)
                    if event.get("type") == "result":
                        success = bool((event.get("result") or {}).get("success"))
                ctx.set_result("success" if success else "error")
                return

            # ESP / esptool path
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

            cmd = [
                *_esptool.resolve_argv(),
                "--chip", "auto", "--port", port, "--baud", "921600",
                WRITE_FLASH_SUBCOMMAND,
                *(["--erase-all"] if req.erase_all else []),
                "0x0", str(fw["merged_bin"]),
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
                            "Board firmware was not updated. Restoring "
                            "USB capture on the previous build…"
                        ),
                    })
                    await source.start()
                elif req.flavor == "ble":
                    yield _ndjson({
                        "type": "line",
                        "stream": "stdout",
                        "text": (
                            f"Flashed BLE firmware -- {source.name} won't "
                            "reconnect over USB (that's expected)."
                        ),
                    })
                else:
                    yield _ndjson({
                        "type": "line",
                        "stream": "stdout",
                        "text": "Waiting for the board to finish rebooting…",
                    })
                    await asyncio.sleep(10.0)
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
