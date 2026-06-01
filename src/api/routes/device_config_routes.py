"""Device identity and map placement for Configuration → GPS."""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from src.api.audit import AuditLogWriter
from src.api.audit.dependencies import get_audit_writer
from src.api.auth.dependencies import require_admin
from src.api.auth.jwt_session import SessionClaims
from src.config import AppConfig, save_section_to_yaml
from src.hal.location.privacy import VALID_LOCATION_PRECISION
from src.transmit.mesh_position_resolver import VALID_MESH_COORDINATE_SOURCES

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


def _sync_registered_identity(device) -> None:
    """Keep upstream Meshradar registration aligned with the wizard pin."""
    if _identity is None:
        return
    _identity.latitude = device.latitude
    _identity.longitude = device.longitude
    _identity.altitude = device.altitude


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
    """GPS card payload.

    The GPS card supports three source modes:

    * ``static`` -- coordinates are entered by the user and live in the
      ``device:`` section of ``local.yaml``. Position is stationary.
    * ``gpsd`` -- live position from a running gpsd daemon (defaults to
      127.0.0.1:2947). The ``location:`` section of ``local.yaml`` holds
      the connection details and update cadence.
    * ``uart`` -- placeholder for the on-board RAK Pi HAT GPS module.
      Not yet wired in v0.7.5; falls back to static.
    """

    source: str = "static"
    # Static-mode fields
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)
    altitude: Optional[float] = Field(None, ge=-500, le=10_000)
    # gpsd-mode fields (all optional; sensible defaults in LocationConfig)
    gpsd_host: Optional[str] = Field(None, min_length=1, max_length=253)
    gpsd_port: Optional[int] = Field(None, ge=1, le=65535)
    update_interval_seconds: Optional[int] = Field(None, ge=1, le=300)
    min_fix_quality: Optional[int] = Field(None, ge=1, le=3)
    # uart-mode fields (kept for forward-compat; not yet wired)
    baud: Optional[int] = Field(None, ge=9600, le=921600)
    timeout_seconds: Optional[int] = Field(None, ge=1, le=3600)
    # Meshtastic POSITION on the LoRa mesh (not Meshradar upstream pin).
    mesh_coordinate_source: Optional[str] = None
    mesh_location_precision: Optional[str] = None


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

    _sync_registered_identity(device)

    return {
        "saved": True,
        "restart_required": True,
        "device": build_device_status(device),
    }


_VALID_GPS_SOURCES = ("static", "gpsd", "uart")


@router.put("/gps")
async def update_gps(
    req: GpsUpdate,
    _claims: SessionClaims = Depends(require_admin),
    audit: AuditLogWriter = Depends(get_audit_writer),
):
    """Persist map coordinates and/or live-GPS connection settings.

    Switching ``source`` requires a service restart because the
    ``LocationSource`` is built once at coordinator startup. Editing
    only the static coordinates while staying on ``static`` is a
    runtime-hot-reload (no restart needed).
    """
    if _config is None:
        raise HTTPException(503, "Config not loaded")

    if req.source not in _VALID_GPS_SOURCES:
        raise HTTPException(
            400,
            f"source must be one of {_VALID_GPS_SOURCES}",
        )

    location = _config.location
    device = _config.device
    source_changed = req.source != location.source

    location_updates: dict = {}
    device_updates: dict = {}
    position_updates: dict = {}

    pos = _config.transmit.position

    # ------------------------------------------------------------------
    # Branch by source: collect all updates, write yaml at the end.
    # ------------------------------------------------------------------
    if req.source == "static":
        if req.latitude is None or req.longitude is None:
            raise HTTPException(
                400,
                "latitude and longitude are required for source=static",
            )
        device.latitude = req.latitude
        device.longitude = req.longitude
        device_updates["latitude"] = req.latitude
        device_updates["longitude"] = req.longitude
        if req.altitude is not None:
            device.altitude = req.altitude
            device_updates["altitude"] = req.altitude
        if source_changed:
            location.source = "static"
            location_updates["source"] = "static"

    elif req.source == "gpsd":
        if source_changed:
            location.source = "gpsd"
            location_updates["source"] = "gpsd"
        if req.gpsd_host is not None and req.gpsd_host != location.gpsd_host:
            location.gpsd_host = req.gpsd_host
            location_updates["gpsd_host"] = req.gpsd_host
        if req.gpsd_port is not None and req.gpsd_port != location.gpsd_port:
            location.gpsd_port = req.gpsd_port
            location_updates["gpsd_port"] = req.gpsd_port
        if (
            req.update_interval_seconds is not None
            and req.update_interval_seconds != location.update_interval_seconds
        ):
            location.update_interval_seconds = req.update_interval_seconds
            location_updates["update_interval_seconds"] = req.update_interval_seconds
        if (
            req.min_fix_quality is not None
            and req.min_fix_quality != location.min_fix_quality
        ):
            location.min_fix_quality = req.min_fix_quality
            location_updates["min_fix_quality"] = req.min_fix_quality
        if req.latitude is not None and req.longitude is not None:
            device.latitude = req.latitude
            device.longitude = req.longitude
            device_updates["latitude"] = req.latitude
            device_updates["longitude"] = req.longitude
            if req.altitude is not None:
                device.altitude = req.altitude
                device_updates["altitude"] = req.altitude

    else:  # uart
        if source_changed:
            location.source = "uart"
            location_updates["source"] = "uart"

    if req.source == "static" and pos.coordinate_source == "live":
        pos.coordinate_source = "static"
        position_updates["coordinate_source"] = "static"

    if req.mesh_coordinate_source is not None:
        mesh_source = req.mesh_coordinate_source.lower()
        if mesh_source not in VALID_MESH_COORDINATE_SOURCES:
            raise HTTPException(
                400,
                f"mesh_coordinate_source must be one of {sorted(VALID_MESH_COORDINATE_SOURCES)}",
            )
        if mesh_source == "live" and req.source == "static":
            raise HTTPException(
                400,
                "Live mesh position requires gpsd or UART as the GPS source",
            )
        if mesh_source != pos.coordinate_source:
            pos.coordinate_source = mesh_source
            position_updates["coordinate_source"] = mesh_source

    if req.mesh_location_precision is not None:
        precision = req.mesh_location_precision.lower()
        if precision not in VALID_LOCATION_PRECISION:
            raise HTTPException(
                400,
                f"mesh_location_precision must be one of {sorted(VALID_LOCATION_PRECISION)}",
            )
        if precision != pos.location_precision:
            pos.location_precision = precision
            position_updates["location_precision"] = precision

    # ------------------------------------------------------------------
    # Persist whatever changed.
    # ------------------------------------------------------------------
    audit_keys = list(location_updates.keys()) + [
        f"device.{k}" for k in device_updates.keys()
    ] + [f"transmit.position.{k}" for k in position_updates.keys()]
    if audit_keys:
        with audit.timed_action(
            user=_claims.subject,
            action="config.gps_update",
            params={"source": req.source, "keys": audit_keys},
        ):
            try:
                if location_updates:
                    save_section_to_yaml("location", asdict(location))
                if device_updates:
                    save_section_to_yaml("device", device_updates)
                if position_updates:
                    save_section_to_yaml(
                        "transmit",
                        {
                            "position": {
                                "interval_minutes": pos.interval_minutes,
                                "startup_delay_seconds": pos.startup_delay_seconds,
                                "coordinate_source": pos.coordinate_source,
                                "location_precision": pos.location_precision,
                            }
                        },
                    )
            except PermissionError as exc:
                raise HTTPException(403, str(exc)) from exc

    if device_updates:
        _sync_registered_identity(device)

    return {
        "saved": bool(audit_keys),
        "restart_required": source_changed,
        "gps": {
            "source": location.source,
            "latitude": device.latitude,
            "longitude": device.longitude,
            "altitude": device.altitude,
            "gpsd_host": location.gpsd_host,
            "gpsd_port": location.gpsd_port,
            "update_interval_seconds": location.update_interval_seconds,
            "min_fix_quality": location.min_fix_quality,
            "mesh_coordinate_source": pos.coordinate_source,
            "mesh_location_precision": pos.location_precision,
        },
    }
