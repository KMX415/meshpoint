"""Extra fields for ``GET /api/config`` beyond the original radio/transmit summary."""

from __future__ import annotations

from src.config import AppConfig


def enrich_config_payload(cfg: AppConfig, base: dict) -> dict:
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
    base["device"] = {
        "device_name": device.device_name,
        "latitude": device.latitude,
        "longitude": device.longitude,
        "altitude": device.altitude,
        "hardware_description": device.hardware_description,
    }
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
    base["capture"] = {
        "sources": list(capture.sources or []),
        "concentrator_spi_device": capture.concentrator_spi_device,
        "meshcore_usb": {
            "serial_port": mc_usb.serial_port,
            "baud_rate": mc_usb.baud_rate,
            "auto_detect": mc_usb.auto_detect,
        },
    }
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
