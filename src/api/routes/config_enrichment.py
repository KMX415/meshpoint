"""Extra fields for ``GET /api/config`` beyond the original radio/transmit summary."""

from __future__ import annotations

from typing import Any, Callable

from src.capture.meshtasticd_module_preset import (
    list_module_presets,
    module_id_from_preset_filename,
)
from src.config import AppConfig


def _preset_badge(preset_file: str) -> str:
    name = (preset_file or "").lower()
    if "13302" in name:
        return "RAK13302"
    if "13300" in name:
        return "RAK13300"
    return ""


def enrich_config_payload(
    cfg: AppConfig,
    base: dict,
    *,
    bridge_status_provider: Callable[[], Any] | None = None,
) -> dict:
    """Merge device, upstream, storage, capture, location, and extended relay/radio into *base*."""
    device = cfg.device
    upstream = cfg.upstream
    storage = cfg.storage
    capture = cfg.capture
    relay = cfg.relay
    radio = cfg.radio
    location = cfg.location
    mc_usb = capture.meshcore_usb

    token = (upstream.auth_token or "").strip()
    platform = device.platform or "gateway"
    base["device"] = {
        "device_name": device.device_name,
        "platform": platform,
        "latitude": device.latitude,
        "longitude": device.longitude,
        "altitude": device.altitude,
        "hardware_description": device.hardware_description,
    }
    if platform == "node":
        base["platform_ui"] = {"variant": "wismesh_node"}
    base["upstream"] = {
        "url": upstream.url,
        "reconnect_interval_seconds": upstream.reconnect_interval_seconds,
        "buffer_max_size": upstream.buffer_max_size,
        "auth_token_set": bool(token),
    }
    base["storage"] = {
        "database_path": storage.database_path,
        "max_packets_retained": storage.max_packets_retained,
        "cleanup_interval_seconds": storage.cleanup_interval_seconds,
    }
    sources = list(capture.sources or [])
    md = capture.meshtasticd
    preset_file = md.preset or ""
    base["capture"] = {
        "sources": sources,
        "concentrator_spi_device": capture.concentrator_spi_device,
        "meshcore_usb": {
            "serial_port": mc_usb.serial_port,
            "baud_rate": mc_usb.baud_rate,
            "auto_detect": mc_usb.auto_detect,
        },
        "meshcore_usb_in_sources": "meshcore_usb" in sources,
        "meshcore_usb_auto_detect_suppressed": platform == "node",
        "meshtasticd": {
            "host": md.host,
            "port": md.port,
            "preset": preset_file,
            "module_badge": _preset_badge(preset_file),
            "active_module_id": module_id_from_preset_filename(preset_file),
            "module_presets": list_module_presets(preset_file),
        },
    }
    if platform == "node":
        base["meshtasticd_runtime"] = _fetch_meshtasticd_runtime(bridge_status_provider)
    base["relay"] = {
        "enabled": relay.enabled,
        "serial_port": relay.serial_port,
        "serial_baud": relay.serial_baud,
        "max_relay_per_minute": relay.max_relay_per_minute,
        "burst_size": relay.burst_size,
        "min_relay_rssi": relay.min_relay_rssi,
        "max_relay_rssi": relay.max_relay_rssi,
    }
    base["radio_advanced"] = {
        "spectral_scan_interval_seconds": radio.spectral_scan_interval_seconds,
        "sx1261_spi_path": radio.sx1261_spi_path or "",
    }
    base["location"] = {
        "source": location.source,
        "gpsd_host": location.gpsd_host,
        "gpsd_port": location.gpsd_port,
        "update_interval_seconds": location.update_interval_seconds,
        "min_fix_quality": location.min_fix_quality,
    }
    pos = cfg.transmit.position
    if "transmit" in base:
        base["transmit"]["position"] = {
            "interval_minutes": pos.interval_minutes,
            "startup_delay_seconds": pos.startup_delay_seconds,
            "coordinate_source": pos.coordinate_source,
            "location_precision": pos.location_precision,
        }
    return base


def _fetch_meshtasticd_runtime(
    bridge_status_provider: Callable[[], Any] | None,
) -> dict[str, Any]:
    """Best-effort live snapshot from the bridge (non-blocking for GET /api/config)."""
    if bridge_status_provider is None:
        return {"bridge_connected": False}
    source = bridge_status_provider()
    if source is None or not getattr(source, "is_running", False):
        return {"bridge_connected": False}
    try:
        ok, detail = source.request_read_radio_state()
        if ok and isinstance(detail, dict):
            return {"bridge_connected": True, **detail}
        return {
            "bridge_connected": True,
            "read_error": str(detail) if detail else "read failed",
        }
    except Exception:
        return {"bridge_connected": True, "read_error": "read failed"}
