"""Live GPS status endpoint that powers the dashboard skyplot.

Single read-only route: ``GET /api/device/gps-status``. Returns the
current ``GpsStatus`` snapshot from the active ``LocationSource``,
including satellites in view (with az/el/SNR), DOP, and device
metadata.

Public-read by design: viewer role can poll it for the skyplot. The
write side -- changing source, gpsd host/port -- lives in
``device_config_routes`` and is admin-only.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.hal.location import GpsStatus, LocationSource

router = APIRouter(prefix="/api/device", tags=["device"])

_location_source: LocationSource | None = None


def init_routes(location_source: LocationSource) -> None:
    global _location_source
    _location_source = location_source


def reset_routes() -> None:
    global _location_source
    _location_source = None


@router.get("/gps-status")
async def gps_status() -> dict:
    """Latest snapshot from the active ``LocationSource``."""
    if _location_source is None:
        raise HTTPException(503, "Location source not initialized")
    status: GpsStatus = _location_source.get_status()
    return status.to_dict()
