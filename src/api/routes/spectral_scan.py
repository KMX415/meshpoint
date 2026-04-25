"""API routes for the spectral scan service."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.spectral.scan_service import ScanService, SweepConfig

router = APIRouter(prefix="/api/spectrum", tags=["spectrum"])

_scan_service: ScanService | None = None


def init_routes(scan_service: ScanService) -> None:
    global _scan_service
    _scan_service = scan_service


class StartScanRequest(BaseModel):
    freq_start_hz: int
    freq_stop_hz: int
    freq_step_hz: int = 200_000
    nb_scan: int = 2000


@router.post("/scan/start")
async def start_scan(req: StartScanRequest):
    if _scan_service is None:
        raise HTTPException(503, "Scan service not initialized")

    if req.freq_start_hz >= req.freq_stop_hz:
        raise HTTPException(422, "freq_start_hz must be less than freq_stop_hz")
    if req.freq_step_hz < 1:
        raise HTTPException(422, "freq_step_hz must be positive")
    if not (100 <= req.nb_scan <= 65535):
        raise HTTPException(422, "nb_scan must be 100–65535")

    cfg = SweepConfig(
        freq_start_hz=req.freq_start_hz,
        freq_stop_hz=req.freq_stop_hz,
        freq_step_hz=req.freq_step_hz,
        nb_scan=req.nb_scan,
    )
    started = _scan_service.start(cfg)
    if not started:
        st = _scan_service.status
        if st.running:
            raise HTTPException(409, "Scan already running")
        raise HTTPException(503, "libloragw unavailable — spectral scan not supported on this hardware")

    return {"status": "started"}


@router.post("/scan/stop")
async def stop_scan():
    if _scan_service is None:
        raise HTTPException(503, "Scan service not initialized")
    _scan_service.stop()
    return {"status": "stopping"}


@router.get("/status")
async def get_status():
    if _scan_service is None:
        return {"running": False, "available": False}
    st = _scan_service.status
    return {
        "running": st.running,
        "available": st.available,
        "freq_start_hz": st.freq_start_hz,
        "freq_stop_hz": st.freq_stop_hz,
        "freq_step_hz": st.freq_step_hz,
        "nb_scan": st.nb_scan,
    }
