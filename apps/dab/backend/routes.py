"""DAB/DAB+ web listener endpoints: tune / stop / status / MP3 stream proxy.

See listener.py for the listener class (wraps a welle-cli subprocess) and
src/audio/sdr_registry.py for why tuning can fail with a 503 while another
RTL-SDR listener (Radio/P2000/Pagers/POCSAG/RTL433) is active -- only one
process can hold the dongle at a time.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import AsyncIterator, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.api.audit import AuditLogWriter
from src.api.audit.dependencies import get_audit_writer
from src.api.auth.dependencies import require_admin
from src.api.auth.jwt_session import SessionClaims
from src.audio import sdr_registry
from src.backup.paths import resolve_meshpoint_root

from .listener import DabListener

router = APIRouter(prefix="/api/dab", tags=["dab"])

_listener: Optional[DabListener] = None

# Registry owner name for a running scan -- distinct from DabListener's own
# "dab" (live tuning/playback), even though they're mutually exclusive
# anyway, so a "busy" message can say which DAB+ activity is holding the
# dongle rather than just "dab" for both.
_SCAN_OWNER = "dab_scan"

# dab_channel_scan.py's default --output, resolved the same
# Mac-dev-vs-Pi-install-portable way as repo_source.py -- MESHPOINT_DIR
# or cwd, so this works whether the server runs from /opt/meshpoint on
# the real device or a plain checkout on a dev machine.
_SCAN_RESULTS_RELATIVE_PATH = Path("config") / "dab_channel_scan.json"

# dab_channel_scan.py lives alongside plugin.toml at the plugin root, one
# level up from this file (backend/routes.py) -- self-contained like every
# other plugin, not under the core repo's scripts/.
_SCAN_SCRIPT_PATH = Path(__file__).resolve().parent.parent / "dab_channel_scan.py"


def _scan_results_path() -> Path:
    return resolve_meshpoint_root() / _SCAN_RESULTS_RELATIVE_PATH


def init_routes(listener: DabListener) -> None:
    global _listener
    _listener = listener


def reset_routes() -> None:
    global _listener
    _listener = None


class TuneRequest(BaseModel):
    channel: str = Field(
        ..., min_length=1, max_length=4,
        description="DAB channel/ensemble code, e.g. 12C",
    )


class ChannelNameUpdate(BaseModel):
    custom_name: str = Field(
        default="", max_length=120,
        description="Display name override; empty string clears it back to the scanned label",
    )


@router.get("/status")
async def dab_status():
    if _listener is None:
        raise HTTPException(503, "Listener not initialised")
    return _listener.poll()


@router.post("/tune")
async def dab_tune(
    req: TuneRequest,
    _claims: SessionClaims = Depends(require_admin),
):
    """Start welle-cli, or retune if already running."""
    if _listener is None:
        raise HTTPException(503, "Listener not initialised")
    try:
        await _listener.tune(req.channel)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    return _listener.status()


@router.post("/stop")
async def dab_stop(_claims: SessionClaims = Depends(require_admin)):
    if _listener is None:
        raise HTTPException(503, "Listener not initialised")
    await _listener.stop()
    return _listener.status()


@router.get("/stream/{sid}")
async def dab_stream(sid: str):
    """Live MP3 for one DAB+ service, proxied from welle-cli's own webserver."""
    if _listener is None:
        raise HTTPException(503, "Listener not initialised")
    if not _listener.running:
        raise HTTPException(409, "Listener not running -- tune first")

    async def _gen():
        async for chunk in _listener.stream(sid):
            yield chunk

    return StreamingResponse(
        _gen(),
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-cache, no-store",
            "X-Accel-Buffering": "no",
        },
    )


def _read_scan_results(path: Path) -> dict:
    if not path.exists():
        raise HTTPException(
            404,
            f"No DAB channel scan results found at {path} -- use the Full scan/Scan specific "
            "channels buttons above to find some.",
        )
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise HTTPException(500, f"Couldn't read scan results at {path}: {exc}")


@router.get("/scan-results")
async def dab_scan_results():
    """Channels dab_channel_scan.py found, read straight from its JSON output."""
    return _read_scan_results(_scan_results_path())


@router.put("/scan-results/{channel}/name")
async def dab_scan_results_set_name(
    channel: str,
    body: ChannelNameUpdate,
    _claims: SessionClaims = Depends(require_admin),
):
    """Set (or, with an empty string, clear) a custom display name for a scanned channel."""
    path = _scan_results_path()
    data = _read_scan_results(path)
    entry = next((c for c in data.get("channels", []) if c.get("channel") == channel), None)
    if entry is None:
        raise HTTPException(404, f"Channel {channel} not found in scan results")

    name = body.custom_name.strip()
    if name:
        entry["custom_name"] = name
    else:
        entry.pop("custom_name", None)
    path.write_text(json.dumps(data, indent=2))
    return entry


def _ndjson(payload: dict) -> bytes:
    return (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")


async def _stream_subprocess(cmd: list[str]) -> AsyncIterator[bytes]:
    """Same NDJSON subprocess-streaming shape as meshtastic_firmware_routes.py/
    pocsag_firmware_routes.py's own helper -- duplicated rather than imported
    since routes.py is otherwise independent of those two modules."""
    yield _ndjson({"type": "started", "cmd": cmd})
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except (FileNotFoundError, OSError) as exc:
        yield _ndjson({
            "type": "result",
            "result": {"returncode": -1, "success": False, "error": str(exc)},
        })
        return

    queue: asyncio.Queue = asyncio.Queue()

    async def pump(stream, name: str) -> None:
        if stream is not None:
            while True:
                line = await stream.readline()
                if not line:
                    break
                await queue.put({
                    "type": "line", "stream": name,
                    "text": line.decode("utf-8", errors="replace").rstrip("\n"),
                })
        await queue.put(None)

    stdout_task = asyncio.create_task(pump(process.stdout, "stdout"))
    stderr_task = asyncio.create_task(pump(process.stderr, "stderr"))

    pending = 2
    while pending:
        item = await queue.get()
        if item is None:
            pending -= 1
            continue
        yield _ndjson(item)

    await stdout_task
    await stderr_task
    returncode = await process.wait()
    yield _ndjson({
        "type": "result",
        "result": {"returncode": returncode, "success": returncode == 0},
    })


class ScanRequest(BaseModel):
    channels: list[str] = Field(
        default_factory=list,
        description="Specific channel codes to scan (e.g. ['7D', '8B']); empty = all 38",
    )
    timeout: float = Field(default=60.0, ge=5.0, le=240.0)
    discard_existing: bool = Field(
        default=False,
        description="Pass --new: discard whatever's already on file instead of merging into it",
    )


@router.post("/scan/stream")
async def dab_scan_stream(
    req: ScanRequest,
    claims: SessionClaims = Depends(require_admin),
    audit: AuditLogWriter = Depends(get_audit_writer),
) -> StreamingResponse:
    """Runs dab_channel_scan.py as a subprocess and streams its output live,
    same NDJSON-over-subprocess shape as the Meshtastic/MeshCore/POCSAG
    firmware-flash cards.

    Claims the RTL-SDR dongle via sdr_registry for the duration, same as
    every other listener -- the script itself talks to welle-cli directly
    and knows nothing about the registry (its own docstring warns "stop
    any active Radio/DAB+/... tab first"), so without this a scan
    triggered from here could silently collide with a live listener
    running in another browser session instead of failing cleanly with
    the same "busy" messaging every other tab already shows.
    """
    try:
        sdr_registry.claim(_SCAN_OWNER)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))

    cmd = [sys.executable, str(_SCAN_SCRIPT_PATH)]
    if req.channels:
        cmd += ["--channels", *req.channels]
    # str(180.0) == "180.0" -- cosmetic only (the script's own --timeout is
    # type=float, "180" and "180.0" parse identically), but the trailing
    # ".0" on every whole-number timeout in the echoed command line was
    # just visual noise for the common case of an admin typing a plain
    # integer into the seconds field.
    timeout_val = req.timeout
    timeout_str = str(int(timeout_val)) if timeout_val == int(timeout_val) else str(timeout_val)
    cmd += ["--timeout", timeout_str]
    if req.discard_existing:
        cmd.append("--new")

    async def body() -> AsyncIterator[bytes]:
        with audit.timed_action(
            user=claims.subject, action="dab.scan",
            params={
                "channels": req.channels or "all", "timeout": req.timeout,
                "discard_existing": req.discard_existing,
            },
        ) as ctx:
            success = False
            try:
                async for chunk in _stream_subprocess(cmd):
                    yield chunk
                    event = json.loads(chunk)
                    if event.get("type") == "result":
                        success = bool((event.get("result") or {}).get("success"))
            finally:
                sdr_registry.release(_SCAN_OWNER)
            ctx.set_result("success" if success else "error")

    return StreamingResponse(
        body(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )
