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
        "blocklist": list(relay.blocklist or []),
        "priority_list": list(relay.priority_list or []),
        "dedup_ttl_seconds": relay.dedup_ttl_seconds,
        "channel_throttle_percent": dict(relay.channel_throttle_percent or {}),
        "storm_guard": {
            "enabled": relay.storm_guard.enabled,
            "window_seconds": relay.storm_guard.window_seconds,
            "identical_packet_threshold": relay.storm_guard.identical_packet_threshold,
            "rate_threshold_per_minute": relay.storm_guard.rate_threshold_per_minute,
            "quarantine_duration_seconds": relay.storm_guard.quarantine_duration_seconds,
            "notify_dashboard": relay.storm_guard.notify_dashboard,
        },
    }
    base["radio_advanced"] = {
        "spectral_scan_interval_seconds": radio.spectral_scan_interval_seconds,
        "sx1261_spi_path": radio.sx1261_spi_path or "",
        "carrier_type": radio.carrier_type or "",
        "gps_pps_enabled": radio.gps_pps_enabled,
        "gps_pps_tty_path": radio.gps_pps_tty_path,
        "gps_family": radio.gps_family,
        "gps_pps_target_baud": radio.gps_pps_target_baud,
    }
    base["location"] = {
        "source": location.source,
        "gpsd_host": location.gpsd_host,
        "gpsd_port": location.gpsd_port,
        "uart_path": location.uart_path,
        "uart_baud": location.uart_baud,
        "update_interval_seconds": location.update_interval_seconds,
        "min_fix_quality": location.min_fix_quality,
    }
    sh = cfg.signal_health
    base["signal_health"] = {
        "green_rssi_floor": sh.green_rssi_floor,
        "yellow_rssi_floor": sh.yellow_rssi_floor,
        "min_packets_per_hour": sh.min_packets_per_hour,
    }
    auto = cfg.automation
    base["automation"] = {
        "enabled": auto.enabled,
        "token_set": bool((auto.token or "").strip()),
    }
    mt = cfg.meshtastic
    base["meshtastic_admin"] = {
        "config_read_available": bool((mt.admin_key_b64 or "").strip()),
        "channel_name": (mt.admin_channel_name or "admin").strip() or "admin",
    }
    return base
