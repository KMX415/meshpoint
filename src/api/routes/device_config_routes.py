"""Device identity and map placement for Configuration → GPS."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.audit import AuditLogWriter
from src.api.audit.dependencies import get_audit_writer
from src.api.auth.dependencies import require_admin
from src.api.auth.jwt_session import SessionClaims
from src.config import AppConfig, save_section_to_yaml

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])

_config: AppConfig | None = None
_identity = None


def init_routes(config: AppConfig, identity=None) -> None:
    global _config, _identity
    _config = config
    _identity = identity


def reset_routes() -> None:
    global _config, _identity
    _config = None
    _identity = None


def build_device_status(device) -> dict:
    return {
        "device_name": device.device_name,
        "latitude": device.latitude,
        "longitude": device.longitude,
        "altitude": device.altitude,
        "hardware_description": device.hardware_description,
    }


class DeviceUpdate(BaseModel):
    device_name: Optional[str] = None
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    altitude: Optional[float] = Field(None, ge=-500, le=10_000)
    hardware_description: Optional[str] = None


class GpsUpdate(BaseModel):
    """GPS card payload: static coordinates map to ``device`` in yaml."""

    source: str = "static"
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    altitude: Optional[float] = Field(None, ge=-500, le=10_000)
    baud: Optional[int] = Field(None, ge=9600, le=921600)
    timeout_seconds: Optional[int] = Field(None, ge=1, le=3600)


@router.put("/device")
async def update_device(
    req: DeviceUpdate,
    _claims: SessionClaims = Depends(require_admin),
    audit: AuditLogWriter = Depends(get_audit_writer),
):
    if _config is None:
        raise HTTPException(503, "Config not loaded")

    updates: dict = {}
    device = _config.device

    if req.device_name is not None:
        name = req.device_name.strip()
        if not name or len(name) > 64:
            raise HTTPException(400, "Device name must be 1-64 characters")
        device.device_name = name
        updates["device_name"] = name
    if req.latitude is not None:
        device.latitude = req.latitude
        updates["latitude"] = req.latitude
    if req.longitude is not None:
        device.longitude = req.longitude
        updates["longitude"] = req.longitude
    if req.altitude is not None:
        device.altitude = req.altitude
        updates["altitude"] = req.altitude
    if req.hardware_description is not None:
        desc = req.hardware_description.strip()
        device.hardware_description = desc
        updates["hardware_description"] = desc

    if not updates:
        return {"saved": False, "restart_required": False, "device": build_device_status(device)}

    with audit.timed_action(
        user=_claims.subject,
        action="config.device_update",
        params={"keys": list(updates.keys())},
    ):
        try:
            save_section_to_yaml("device", updates)
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc

    return {
        "saved": True,
        "restart_required": True,
        "device": build_device_status(device),
    }


@router.put("/gps")
async def update_gps(
    req: GpsUpdate,
    _claims: SessionClaims = Depends(require_admin),
    audit: AuditLogWriter = Depends(get_audit_writer),
):
    """Persist map coordinates. UART source is informational until gpsd lands."""
    if _config is None:
        raise HTTPException(503, "Config not loaded")

    if req.source not in ("uart", "static"):
        raise HTTPException(400, "source must be uart or static")

    if req.source == "uart":
        return {
            "saved": True,
            "restart_required": False,
            "gps": {"source": "uart", "note": "Live UART GPS uses the on-board module; edit coordinates under static mode."},
        }

    if req.latitude is None or req.longitude is None:
        raise HTTPException(400, "latitude and longitude are required for static GPS")

    device_req = DeviceUpdate(
        latitude=req.latitude,
        longitude=req.longitude,
        altitude=req.altitude,
    )
    result = await update_device(device_req, _claims, audit)
    result["gps"] = {
        "source": "static",
        "latitude": req.latitude,
        "longitude": req.longitude,
        "altitude": req.altitude,
    }
    return result
