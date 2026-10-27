"""RTL-SDR web listener endpoints: tune / stop / status / MP3 stream.

The stream endpoint relies on the session cookie for auth (the router is
registered with the standard ``protected`` dependencies), so a plain
``<audio src="/api/listener/stream">`` element works from the dashboard.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from src.api.auth.dependencies import require_admin
from src.api.auth.jwt_session import SessionClaims

from .listener import MAX_FREQ_HZ, MIN_FREQ_HZ, RtlListener

router = APIRouter(prefix="/api/listener", tags=["listener"])

_listener: RtlListener | None = None


def init_routes(listener: RtlListener) -> None:
    global _listener
    _listener = listener


def reset_routes() -> None:
    global _listener
    _listener = None


class TuneRequest(BaseModel):
    frequency_mhz: float = Field(
        ge=MIN_FREQ_HZ / 1e6, le=MAX_FREQ_HZ / 1e6,
        description="Centre frequency in MHz (R820T range 24-1766)",
    )
    deemphasis_us: Optional[int] = Field(None, description="FM audio correction: 50 or 75 microseconds")
    mode: str = Field("nfm", description="nfm | am | usb | lsb | wfm")
    squelch: int = Field(0, ge=0, le=1000)
    gain: Optional[float] = Field(None, ge=0, le=50, description="dB; omit for AGC")
    volume: Optional[float] = Field(
        None, ge=0.05, le=1.5,
        description="pre-encoder level; omit to keep current",
    )
    station_label: str = Field(
        "", description="Preset name, if tuned via a preset; empty for a manual frequency tune",
    )


@router.get("/status")
async def listener_status():
    if _listener is None:
        raise HTTPException(503, "Listener not initialised")
    return _listener.status()


@router.post("/tune")
async def listener_tune(
    req: TuneRequest,
    _claims: SessionClaims = Depends(require_admin),
):
    """Start the pipeline, or retune if already running."""
    if _listener is None:
        raise HTTPException(503, "Listener not initialised")
    try:
        await _listener.tune(
            frequency_hz=int(round(req.frequency_mhz * 1e6)),
            mode=req.mode,
            squelch=req.squelch,
            gain=req.gain,
            volume=req.volume,
            station_label=req.station_label,
            deemphasis_us=req.deemphasis_us,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    return _listener.status()


@router.post("/stop")
async def listener_stop(_claims: SessionClaims = Depends(require_admin)):
    if _listener is None:
        raise HTTPException(503, "Listener not initialised")
    await _listener.stop()
    return _listener.status()


@router.get("/stream")
async def listener_stream():
    """Live MP3 audio. One subscriber per request; ends when tuning stops."""
    if _listener is None:
        raise HTTPException(503, "Listener not initialised")
    if not _listener.running:
        raise HTTPException(409, "Listener not running -- tune first")

    queue = _listener.subscribe()

    async def _gen():
        try:
            while True:
                chunk = await queue.get()
                if not chunk:  # b"" sentinel: pipeline ended
                    return
                yield chunk
        finally:
            _listener.unsubscribe(queue)

    return StreamingResponse(
        _gen(),
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-cache, no-store",
            "X-Accel-Buffering": "no",
        },
    )
