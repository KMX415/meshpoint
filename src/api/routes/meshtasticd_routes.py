"""REST API for WisMesh Node (meshtasticd) radio control."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.capture.meshtasticd_module_preset import (
    list_module_presets,
    module_id_from_preset_filename,
    resolve_module_preset,
)
from src.config import AppConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/meshtasticd", tags=["meshtasticd"])

_config: AppConfig | None = None
_bridge_accessor: Callable[[], Any] | None = None


def init_routes(
    config: AppConfig,
    bridge_accessor: Callable[[], Any] | None = None,
) -> None:
    global _config, _bridge_accessor
    _config = config
    _bridge_accessor = bridge_accessor


def _require_node_platform() -> None:
    if _config is None:
        raise HTTPException(503, "Config not loaded")
    if _config.device.platform != "node":
        raise HTTPException(
            400,
            "meshtasticd control is only available on WisMesh Node platform",
        )


def _get_bridge_source():
    if _bridge_accessor is None:
        return None
    return _bridge_accessor()


def _preset_badge(preset_file: str) -> str:
    name = (preset_file or "").lower()
    if "13302" in name:
        return "RAK13302"
    if "13300" in name:
        return "RAK13300"
    return ""


def build_meshtasticd_status(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge yaml config with optional live bridge snapshot."""
    if _config is None:
        return {"available": False}

    md = _config.capture.meshtasticd
    preset_file = md.preset or ""
    payload: dict[str, Any] = {
        "available": _config.device.platform == "node",
        "bridge_connected": False,
        "host": md.host,
        "port": md.port,
        "preset_file": preset_file,
        "module_badge": _preset_badge(preset_file),
        "local_node_id_hex": "",
        "long_name": "",
        "short_name": "",
        "hw_model": 37,
        "region": _config.radio.region,
        "modem_preset": "",
        "tx_power_dbm": 0,
        "tx_enabled": True,
        "firmware_version": "",
        "primary_channel_name": _config.meshtastic.primary_channel_name,
    }
    payload["module_presets"] = list_module_presets(preset_file)
    payload["active_module_id"] = module_id_from_preset_filename(preset_file)
    if extra:
        payload.update(extra)
    return payload


@router.get("/status")
async def get_meshtasticd_status():
    """Live meshtasticd owner + LoRa snapshot for WisMesh dashboard cards."""
    _require_node_platform()
    extra: dict[str, Any] = {}
    source = _get_bridge_source()
    if source is not None and source.is_running:
        ok, detail = await asyncio.to_thread(source.request_read_radio_state)
        if ok and isinstance(detail, dict):
            extra = {
                "bridge_connected": True,
                **detail,
            }
        else:
            extra["bridge_connected"] = True
            extra["read_error"] = str(detail) if detail else "read failed"
    return build_meshtasticd_status(extra)


class MeshtasticdIdentityUpdate(BaseModel):
    long_name: str = Field(..., min_length=1, max_length=36)
    short_name: str = Field(..., min_length=1, max_length=4)


class MeshtasticdRadioUpdate(BaseModel):
    region: Optional[str] = None
    modem_preset: Optional[str] = None
    tx_power_dbm: Optional[int] = None
    tx_enabled: Optional[bool] = None
    primary_channel_name: Optional[str] = None


@router.put("/identity")
async def update_meshtasticd_identity(req: MeshtasticdIdentityUpdate):
    """Push long/short name to meshtasticd via setOwner."""
    _require_node_platform()
    source = _get_bridge_source()
    if source is None or not source.is_running:
        raise HTTPException(503, "meshtasticd bridge not connected")

    ok, detail = await asyncio.to_thread(
        source.request_write_owner,
        req.long_name.strip(),
        req.short_name.strip(),
    )
    if not ok:
        raise HTTPException(502, detail or "setOwner failed")
    return {"saved": True, "long_name": req.long_name, "short_name": req.short_name}


@router.put("/radio")
async def update_meshtasticd_radio(req: MeshtasticdRadioUpdate):
    """Push LoRa preferences to meshtasticd via writeConfig."""
    _require_node_platform()
    source = _get_bridge_source()
    if source is None or not source.is_running:
        raise HTTPException(503, "meshtasticd bridge not connected")

    payload = req.model_dump(exclude_none=True)
    if not payload:
        return {"saved": False, "changes": []}

    ok, detail = await asyncio.to_thread(source.request_write_lora, payload)
    if not ok:
        raise HTTPException(502, str(detail) if detail else "write failed")
    changes = detail.get("changes", []) if isinstance(detail, dict) else []
    return {"saved": True, "changes": changes}


class ModulePresetUpdate(BaseModel):
    module_id: str = Field(..., pattern=r"^(13300|13302)$")


@router.get("/module-presets")
async def get_module_presets():
    """Catalog of RAK13300 / RAK13302 WisBlock profiles for the WisMesh HAT."""
    _require_node_platform()
    preset = _config.capture.meshtasticd.preset if _config else ""
    return {"presets": list_module_presets(preset)}


@router.put("/module-preset")
async def update_module_preset(req: ModulePresetUpdate):
    """Install the meshtasticd LoRa yaml for the selected WisBlock module."""
    _require_node_platform()
    if _config is None:
        raise HTTPException(503, "Config not loaded")

    current = module_id_from_preset_filename(_config.capture.meshtasticd.preset)
    if current == req.module_id:
        entry = resolve_module_preset(req.module_id)
        return {
            "applied": False,
            "already_active": True,
            "module_id": entry.module_id,
            "preset_file": entry.filename,
            "label": entry.label,
            "meshpoint_restart_recommended": False,
        }

    try:
        from src.capture.meshtasticd_module_preset import apply_module_preset

        md = _config.capture.meshtasticd
        result = await asyncio.to_thread(
            apply_module_preset,
            req.module_id,
            host=md.host,
            port=md.port,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(503, str(exc)) from exc
    except (RuntimeError, TimeoutError) as exc:
        raise HTTPException(502, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc

    _config.capture.meshtasticd.preset = result["preset_file"]
    return result
