"""ADS-B (air traffic, dump1090) endpoints: start / stop / status.

See ``listener.py`` for the listener class, and ``src/audio/sdr_registry.py``
for why starting this can fail with a 503 while another RTL-SDR listener is
active (only one process can hold the dongle at a time; manual stop
required by design).
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.auth.dependencies import require_admin
from src.api.auth.jwt_session import SessionClaims

from .listener import AdsbListener

router = APIRouter(prefix="/api/adsb", tags=["adsb"])

_listener: Optional[AdsbListener] = None


class StartRequest(BaseModel):
    metric: bool = Field(
        default=True,
        description="Pass dump1090's --metric flag (meters/km/h instead of feet/knots)",
    )


def init_routes(listener: AdsbListener) -> None:
    global _listener
    _listener = listener


def reset_routes() -> None:
    global _listener
    _listener = None


@router.get("/status")
async def status():
    if _listener is None:
        raise HTTPException(503, "Listener not initialised")
    return _listener.poll()


@router.post("/start")
async def start(
    req: StartRequest = StartRequest(),
    _claims: SessionClaims = Depends(require_admin),
):
    if _listener is None:
        raise HTTPException(503, "Listener not initialised")
    try:
        await _listener.start(metric=req.metric)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    return _listener.status()


@router.post("/stop")
async def stop(_claims: SessionClaims = Depends(require_admin)):
    if _listener is None:
        raise HTTPException(503, "Listener not initialised")
    await _listener.stop()
    return _listener.status()
