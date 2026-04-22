"""REST API endpoints for Meshpoint configuration.

Provides read/write access to radio, transmit, channel, and identity
settings. Runtime-safe changes apply immediately; RX-affecting changes
flag restart_required in the response.
"""

from __future__ import annotations

import logging
import subprocess
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.config import AppConfig, save_section_to_yaml
from src.radio.presets import (
    REGION_DEFAULTS,
    SUPPORTED_REGIONS,
    all_presets_list,
    get_preset,
    preset_from_params,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/config", tags=["config"])

_config: AppConfig | None = None
_crypto = None
_tx_service = None


def init_routes(
    config: AppConfig,
    crypto=None,
    tx_service=None,
) -> None:
    global _config, _crypto, _tx_service
    _config = config
    _crypto = crypto
    _tx_service = tx_service


@router.get("")
async def get_config():
    """Full configuration summary for the Radio tab."""
    if _config is None:
        raise HTTPException(503, "Config not loaded")

    radio = _config.radio
    tx = _config.transmit
    mt = _config.meshtastic

    current_preset = preset_from_params(
        radio.spreading_factor, radio.bandwidth_khz, radio.coding_rate
    )

    channels = _build_channel_list(mt)

    mc_status = {"connected": False, "companion_name": "", "radio": {}}
    if _tx_service and hasattr(_tx_service, "_meshcore_tx"):
        mc_tx = _tx_service._meshcore_tx
        if mc_tx and mc_tx.connected:
            mc_status["connected"] = True
            try:
                radio_info = await mc_tx.get_radio_info()
                if radio_info:
                    mc_status["companion_name"] = radio_info.name
                    mc_status["radio"] = {
                        "frequency_mhz": radio_info.frequency_mhz,
                        "bandwidth_khz": radio_info.bandwidth_khz,
                        "spreading_factor": radio_info.spreading_factor,
                        "tx_power": radio_info.tx_power,
                    }
            except Exception:
                pass

    duty_info = {"used_percent": 0.0, "remaining_ms": 0}
    if _tx_service and hasattr(_tx_service, "_duty"):
        duty = _tx_service._duty
        if duty:
            duty_info["used_percent"] = round(duty.current_usage_percent(), 2)
            duty_info["remaining_ms"] = duty.remaining_budget_ms()

    node_id_hex = f"!{tx.node_id:08x}" if tx.node_id else ""

    return {
        "radio": {
            "region": radio.region,
            "frequency_mhz": radio.frequency_mhz,
            "spreading_factor": radio.spreading_factor,
            "bandwidth_khz": radio.bandwidth_khz,
            "coding_rate": radio.coding_rate,
            "sync_word": f"0x{radio.sync_word:02X}",
            "preamble_length": radio.preamble_length,
            "current_preset": current_preset,
            "concentrator_slots": radio.concentrator_slots,
        },
        "transmit": {
            "enabled": tx.enabled,
            "node_id": tx.node_id,
            "node_id_hex": node_id_hex,
            "tx_power_dbm": tx.tx_power_dbm,
            "max_duty_cycle_percent": tx.max_duty_cycle_percent,
            "long_name": tx.long_name,
            "short_name": tx.short_name,
            "hop_limit": tx.hop_limit,
        },
        "channels": channels,
        "meshcore": mc_status,
        "duty_cycle": duty_info,
        "presets": all_presets_list(),
        "regions": [
            {"id": r, "name": d["name"], "frequency_mhz": d["frequency_mhz"]}
            for r, d in REGION_DEFAULTS.items()
        ],
    }


class TransmitUpdate(BaseModel):
    enabled: Optional[bool] = None
    tx_power_dbm: Optional[int] = None
    max_duty_cycle_percent: Optional[float] = None
    hop_limit: Optional[int] = None


@router.put("/transmit")
async def update_transmit(req: TransmitUpdate):
    """Update TX settings. Some changes require a restart."""
    if _config is None:
        raise HTTPException(503, "Config not loaded")

    updates = {}
    tx = _config.transmit
    restart_needed = False

    if req.enabled is not None:
        tx.enabled = req.enabled
        updates["enabled"] = req.enabled
        restart_needed = True
    if req.tx_power_dbm is not None:
        if not 0 <= req.tx_power_dbm <= 30:
            raise HTTPException(400, "TX power must be 0-30 dBm")
        tx.tx_power_dbm = req.tx_power_dbm
        updates["tx_power_dbm"] = req.tx_power_dbm
    if req.max_duty_cycle_percent is not None:
        if not 0.1 <= req.max_duty_cycle_percent <= 100:
            raise HTTPException(400, "Duty cycle must be 0.1-100%")
        tx.max_duty_cycle_percent = req.max_duty_cycle_percent
        updates["max_duty_cycle_percent"] = req.max_duty_cycle_percent
    if req.hop_limit is not None:
        if not 0 <= req.hop_limit <= 7:
            raise HTTPException(400, "Hop limit must be 0-7")
        tx.hop_limit = req.hop_limit
        updates["hop_limit"] = req.hop_limit

    if updates:
        try:
            save_section_to_yaml("transmit", updates)
        except PermissionError as exc:
            raise HTTPException(403, str(exc))

    return {"saved": True, "restart_required": restart_needed, "updates": updates}


class IdentityUpdate(BaseModel):
    long_name: Optional[str] = None
    short_name: Optional[str] = None
    node_id: Optional[int] = None


@router.put("/identity")
async def update_identity(req: IdentityUpdate):
    """Update node identity. node_id changes need restart."""
    if _config is None:
        raise HTTPException(503, "Config not loaded")

    updates = {}
    tx = _config.transmit
    restart_needed = False

    if req.long_name is not None:
        if len(req.long_name) > 36:
            raise HTTPException(400, "Long name max 36 characters")
        tx.long_name = req.long_name
        updates["long_name"] = req.long_name
    if req.short_name is not None:
        if len(req.short_name) > 4:
            raise HTTPException(400, "Short name max 4 characters")
        tx.short_name = req.short_name
        updates["short_name"] = req.short_name
    if req.node_id is not None:
        tx.node_id = req.node_id
        updates["node_id"] = req.node_id
        restart_needed = True

    if updates:
        try:
            save_section_to_yaml("transmit", updates)
        except PermissionError as exc:
            raise HTTPException(403, str(exc))

    return {"saved": True, "restart_required": restart_needed, "updates": updates}


class RadioUpdate(BaseModel):
    region: Optional[str] = None
    preset: Optional[str] = None
    frequency_mhz: Optional[float] = None
    spreading_factor: Optional[int] = None
    bandwidth_khz: Optional[float] = None
    coding_rate: Optional[str] = None


@router.put("/radio")
async def update_radio(req: RadioUpdate):
    """Update radio settings. Flags restart_required for RX changes."""
    if _config is None:
        raise HTTPException(503, "Config not loaded")

    updates = {}
    radio = _config.radio
    restart_needed = False

    if req.region is not None:
        if req.region not in SUPPORTED_REGIONS:
            raise HTTPException(400, f"Unknown region: {req.region}")
        if req.region != radio.region:
            restart_needed = True
        updates["region"] = req.region

    if req.preset is not None:
        preset = get_preset(req.preset)
        if not preset:
            raise HTTPException(400, f"Unknown preset: {req.preset}")
        updates["spreading_factor"] = preset.spreading_factor
        updates["bandwidth_khz"] = preset.bandwidth_khz
        updates["coding_rate"] = preset.coding_rate
        if (
            preset.spreading_factor != radio.spreading_factor
            or preset.bandwidth_khz != radio.bandwidth_khz
            or preset.coding_rate != radio.coding_rate
        ):
            restart_needed = True
    else:
        if req.spreading_factor is not None:
            if req.spreading_factor != radio.spreading_factor:
                restart_needed = True
            updates["spreading_factor"] = req.spreading_factor
        if req.bandwidth_khz is not None:
            if req.bandwidth_khz != radio.bandwidth_khz:
                restart_needed = True
            updates["bandwidth_khz"] = req.bandwidth_khz
        if req.coding_rate is not None:
            valid_rates = {"4/5", "4/6", "4/7", "4/8"}
            if req.coding_rate not in valid_rates:
                raise HTTPException(400, f"Invalid coding rate: {req.coding_rate}")
            if req.coding_rate != radio.coding_rate:
                restart_needed = True
            updates["coding_rate"] = req.coding_rate

    if req.frequency_mhz is not None:
        if req.frequency_mhz != radio.frequency_mhz:
            restart_needed = True
        updates["frequency_mhz"] = req.frequency_mhz
    elif req.region and req.region in REGION_DEFAULTS and "frequency_mhz" not in updates:
        updates["frequency_mhz"] = REGION_DEFAULTS[req.region]["frequency_mhz"]

    if updates:
        try:
            save_section_to_yaml("radio", updates)
        except PermissionError as exc:
            raise HTTPException(403, str(exc))

    return {
        "saved": True,
        "restart_required": restart_needed,
        "updates": updates,
    }


class ChannelEntry(BaseModel):
    index: int = -1
    name: str = ""
    psk_b64: str = ""
    enabled: bool = True
    concentrator_slot: Optional[int] = None


class ChannelsUpdate(BaseModel):
    channels: list[ChannelEntry]


class ConcentratorSlotEntry(BaseModel):
    slot_index: int
    preset: str
    frequency_slot: int
    enabled: bool = True


class ConcentratorSlotsUpdate(BaseModel):
    slots: list[ConcentratorSlotEntry]


@router.put("/channels")
async def update_channels(req: ChannelsUpdate):
    """Update channel keys. Applies to crypto at runtime (no restart)."""
    if _config is None:
        raise HTTPException(503, "Config not loaded")

    channel_keys = {}
    channel_slots = {}
    for ch in req.channels:
        if ch.index == 0:
            _config.meshtastic.primary_channel_name = ch.name
            try:
                save_section_to_yaml(
                    "meshtastic", {"primary_channel_name": ch.name}
                )
            except PermissionError as exc:
                raise HTTPException(403, str(exc))
            continue

        if ch.enabled and ch.psk_b64:
            channel_keys[ch.name] = ch.psk_b64
            if ch.concentrator_slot is not None:
                channel_slots[ch.name] = ch.concentrator_slot

    _config.meshtastic.channel_keys = channel_keys
    _config.meshtastic.channel_slots = channel_slots
    try:
        save_section_to_yaml("meshtastic", {
            "channel_keys": channel_keys,
            "channel_slots": channel_slots,
        })
    except PermissionError as exc:
        raise HTTPException(403, str(exc))

    if _crypto and hasattr(_crypto, "add_channel_key"):
        for name, key_b64 in channel_keys.items():
            _crypto.add_channel_key(name, key_b64)

    return {
        "saved": True,
        "restart_required": False,
        "channel_count": len(channel_keys) + 1,
    }


@router.put("/concentrator-slots")
async def update_concentrator_slots(req: ConcentratorSlotsUpdate):
    """Update per-IF-chain concentrator slot configuration. Requires restart."""
    if _config is None:
        raise HTTPException(503, "Config not loaded")

    valid_presets = {p["name"] for p in all_presets_list()}
    slots = []
    for s in req.slots:
        if not 0 <= s.slot_index <= 7:
            raise HTTPException(400, f"slot_index must be 0–7, got {s.slot_index}")
        if s.preset not in valid_presets:
            raise HTTPException(400, f"Unknown preset: {s.preset}")
        if s.frequency_slot < 0:
            raise HTTPException(400, "frequency_slot must be >= 0")
        slots.append({
            "slot_index": s.slot_index,
            "preset": s.preset,
            "frequency_slot": s.frequency_slot,
            "enabled": s.enabled,
        })

    _config.radio.concentrator_slots = slots
    try:
        save_section_to_yaml("radio", {"concentrator_slots": slots})
    except PermissionError as exc:
        raise HTTPException(403, str(exc))

    return {"saved": True, "restart_required": True, "slot_count": len(slots)}


@router.post("/restart")
async def restart_service():
    """Trigger a service restart via systemctl."""
    try:
        subprocess.Popen(  # nosec B603 B607
            ["sudo", "systemctl", "restart", "meshpoint"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return {"status": "restarting"}
    except Exception as exc:
        raise HTTPException(500, f"Restart failed: {exc}")


def _build_channel_list(mt_config) -> list[dict]:
    """Build the channel list from config + crypto state."""
    ch0_name = mt_config.primary_channel_name
    if not ch0_name and _config and _config.radio:
        from src.transmit.tx_service import PRESET_DISPLAY_NAMES
        sf = _config.radio.spreading_factor
        bw = int(_config.radio.bandwidth_khz)
        ch0_name = PRESET_DISPLAY_NAMES.get((sf, bw), "LongFast")

    ch0_name = ch0_name or "LongFast"

    channels = [
        {
            "index": 0,
            "name": ch0_name,
            "hash_name": ch0_name,
            "psk_b64": mt_config.default_key_b64,
            "hash": _compute_hash_safe(ch0_name, mt_config.default_key_b64),
            "enabled": True,
        }
    ]

    for i, (name, key_b64) in enumerate(mt_config.channel_keys.items(), start=1):
        channels.append({
            "index": i,
            "name": name,
            "psk_b64": key_b64,
            "hash": _compute_hash_safe(name, key_b64),
            "enabled": True,
            "concentrator_slot": mt_config.channel_slots.get(name),
        })

    return channels


def _compute_hash_safe(name: str, key_b64: str) -> str:
    """Compute channel hash, returning hex string or '--' on error."""
    if _crypto and hasattr(_crypto, "compute_channel_hash"):
        try:
            import base64
            expanded = _crypto._expand_key(base64.b64decode(key_b64))
            h = _crypto.compute_channel_hash(name, expanded)
            return f"0x{h:02X}"
        except Exception:
            pass
    return "--"
